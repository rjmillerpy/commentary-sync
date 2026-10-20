# LiveKit's VM: WebRTC needs UDP and a fixed public IP, which Fargate behind
# a load balancer can't give. It also runs Egress (HLS recording, uploaded to
# S3), Redis (LiveKit's and Egress's, and the API's rate limits, listener
# counts and sync references) and Caddy (TLS for wss://live.<domain>).
# Configured entirely by cloud-init (templates/livekit-cloud-init.yaml.tftpl);
# reached by Session Manager, never SSH: no key, no port 22.

data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

resource "aws_eip" "livekit" {
  domain = "vpc"
  tags   = { Name = "${var.project}-livekit" }
}

resource "aws_instance" "livekit" {
  ami                    = data.aws_ssm_parameter.al2023.value
  instance_type          = var.livekit_instance_type
  subnet_id              = aws_subnet.public[0].id
  vpc_security_group_ids = [aws_security_group.livekit.id]
  iam_instance_profile   = aws_iam_instance_profile.livekit.name
  monitoring             = false # checkov:skip=CKV_AWS_126:Detailed monitoring is $2/month; the status-check alarm uses the free metrics
  ebs_optimized          = true

  user_data_replace_on_change = true
  user_data = templatefile("${path.module}/templates/livekit-cloud-init.yaml.tftpl", {
    region        = var.region
    ssm_prefix    = local.ssm_prefix
    public_ip     = aws_eip.livekit.public_ip
    live_host     = local.hosts.live
    webhook_url   = "https://${local.hosts.api}/webhooks/livekit"
    hls_bucket    = aws_s3_bucket.hls.bucket
    livekit_image = "livekit/livekit-server:v1.13.7"
    egress_image  = "livekit/egress:v1.14.1"
    redis_image   = "redis:8.10.2-alpine"
    caddy_image   = "caddy:2.11.4-alpine"
    livekit_http  = local.ports.livekit_http
    redis_port    = local.ports.redis
    ice_tcp       = local.ports.ice_tcp
    ice_udp       = local.ports.ice_udp
  })

  metadata_options {
    http_tokens                 = "required" # IMDSv2 only
    http_put_response_hop_limit = 1          # every container is on the host network
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = 20
    encrypted   = true
  }

  tags = { Name = "${var.project}-livekit" }
}

resource "aws_eip_association" "livekit" {
  instance_id   = aws_instance.livekit.id
  allocation_id = aws_eip.livekit.id
}
