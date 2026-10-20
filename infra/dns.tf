# The domain's hosted zone exists already (registering a domain with Route 53
# creates it; $0.50 a month). Certificates are validated through DNS, so they
# renew without anyone.

data "aws_route53_zone" "main" {
  name = var.domain_name
}

# The load balancer's: the API and the studio.
resource "aws_acm_certificate" "regional" {
  domain_name               = local.hosts.api
  subject_alternative_names = [local.hosts.studio]
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

# CloudFront's, which must live in us-east-1.
resource "aws_acm_certificate" "hls" {
  provider          = aws.us_east_1
  domain_name       = local.hosts.hls
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

locals {
  # Keyed by host name, known at plan time (ACM's own answer isn't until apply).
  certificate_hosts = {
    (local.hosts.api)    = aws_acm_certificate.regional
    (local.hosts.studio) = aws_acm_certificate.regional
    (local.hosts.hls)    = aws_acm_certificate.hls
  }
}

resource "aws_route53_record" "validation" {
  for_each = local.certificate_hosts

  zone_id         = data.aws_route53_zone.main.zone_id
  allow_overwrite = true
  name            = one([for option in each.value.domain_validation_options : option.resource_record_name if option.domain_name == each.key])
  type            = one([for option in each.value.domain_validation_options : option.resource_record_type if option.domain_name == each.key])
  records         = [one([for option in each.value.domain_validation_options : option.resource_record_value if option.domain_name == each.key])]
  ttl             = 300
}

resource "aws_acm_certificate_validation" "regional" {
  certificate_arn         = aws_acm_certificate.regional.arn
  validation_record_fqdns = [aws_route53_record.validation[local.hosts.api].fqdn, aws_route53_record.validation[local.hosts.studio].fqdn]
}

resource "aws_acm_certificate_validation" "hls" {
  provider                = aws.us_east_1
  certificate_arn         = aws_acm_certificate.hls.arn
  validation_record_fqdns = [aws_route53_record.validation[local.hosts.hls].fqdn]
}

resource "aws_route53_record" "alb" {
  for_each = toset([local.hosts.api, local.hosts.studio])

  zone_id = data.aws_route53_zone.main.zone_id
  name    = each.key
  type    = "A"

  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = true
  }
}

resource "aws_route53_record" "hls" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = local.hosts.hls
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.hls.domain_name
    zone_id                = aws_cloudfront_distribution.hls.hosted_zone_id
    evaluate_target_health = false
  }
}

# LiveKit's VM, directly: WebRTC can't go through the load balancer. Caddy on
# the VM gets its own certificate (Let's Encrypt) for wss.
resource "aws_route53_record" "live" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = local.hosts.live
  type    = "A"
  ttl     = 300
  records = [aws_eip.livekit.public_ip]
}
