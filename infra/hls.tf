# The HLS recordings: Egress uploads them to a private bucket, CloudFront
# serves them at https://hls.<domain>. Only CloudFront can read the bucket
# (origin access control). A recording's random path is the key to it, as
# locally; CloudFront signed cookies are the next step (README).

resource "aws_s3_bucket" "hls" {
  bucket        = "${var.project}-hls-${local.account_id}"
  force_destroy = true # segments are temporary: a destroy needn't wait on emptying it by hand
  # checkov:skip=CKV_AWS_18:Access logs would cost more than the segments they log
  # checkov:skip=CKV_AWS_21:Versioning would keep every expired segment; they are meant to go
  # checkov:skip=CKV_AWS_144:Cross-region copies of three-day-old audio segments have no use
  # checkov:skip=CKV_AWS_145:SSE-S3 (below); a customer KMS key is $1/month and per-request charges
  # checkov:skip=CKV2_AWS_62:Nothing listens for bucket events
}

resource "aws_s3_bucket_public_access_block" "hls" {
  bucket                  = aws_s3_bucket.hls.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "hls" {
  bucket = aws_s3_bucket.hls.id
  rule {
    object_ownership = "BucketOwnerEnforced" # no ACLs at all
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "hls" {
  bucket = aws_s3_bucket.hls.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "hls" {
  bucket = aws_s3_bucket.hls.id
  rule {
    id     = "expire-recordings"
    status = "Enabled"
    filter {}
    expiration {
      days = var.hls_retention_days
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

resource "aws_s3_bucket_policy" "hls" {
  bucket = aws_s3_bucket.hls.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "CloudFrontReadsOnly"
        Effect    = "Allow"
        Principal = { Service = "cloudfront.amazonaws.com" }
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.hls.arn}/*"
        Condition = { StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.hls.arn } }
      },
      {
        Sid       = "TlsOnly"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [aws_s3_bucket.hls.arn, "${aws_s3_bucket.hls.arn}/*"]
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      },
    ]
  })
  depends_on = [aws_s3_bucket_public_access_block.hls]
}

resource "aws_cloudfront_origin_access_control" "hls" {
  name                              = "${var.project}-hls"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

data "aws_cloudfront_cache_policy" "managed" {
  for_each = { optimized = "Managed-CachingOptimized", disabled = "Managed-CachingDisabled" }
  name     = each.value
}

# Players fetch from the studio and the app across origins; any origin may
# read, as locally (deploy/hls-nginx.conf).
resource "aws_cloudfront_response_headers_policy" "hls" {
  name = "${var.project}-hls"

  cors_config {
    access_control_allow_credentials = false
    origin_override                  = true
    access_control_allow_headers {
      items = ["*"]
    }
    access_control_allow_methods {
      items = ["GET", "HEAD"]
    }
    access_control_allow_origins {
      items = ["*"]
    }
  }

  security_headers_config {
    content_type_options {
      override = true
    }
    strict_transport_security {
      access_control_max_age_sec = 31536000
      include_subdomains         = true
      preload                    = true
      override                   = true
    }
  }
}

resource "aws_cloudfront_distribution" "hls" {
  enabled         = true
  is_ipv6_enabled = true
  comment         = "${var.project} HLS"
  price_class     = "PriceClass_100" # North America and Europe: the cheapest
  # checkov:skip=CKV_AWS_305:There is no root page: only playlists and segments at unguessable paths
  aliases = [local.hosts.hls]
  # checkov:skip=CKV_AWS_68:A WAF is $5/month plus rules; the paths are unguessable
  # checkov:skip=CKV_AWS_86:Access logs would cost more than they show at this size
  # checkov:skip=CKV_AWS_310:One origin: there is nothing to fail over to
  # checkov:skip=CKV_AWS_374:Listeners can be anywhere
  # checkov:skip=CKV2_AWS_47:The WAF's Log4j rule set needs a WAF (CKV_AWS_68)

  origin {
    origin_id                = "hls-bucket"
    domain_name              = aws_s3_bucket.hls.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.hls.id
  }

  # Segments never change: cached.
  default_cache_behavior {
    target_origin_id           = "hls-bucket"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = false # audio segments don't compress
    cache_policy_id            = data.aws_cloudfront_cache_policy.managed["optimized"].id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.hls.id
  }

  # The playlist changes every segment: never cached.
  ordered_cache_behavior {
    path_pattern               = "*.m3u8"
    target_origin_id           = "hls-bucket"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = data.aws_cloudfront_cache_policy.managed["disabled"].id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.hls.id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.hls.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }
}
