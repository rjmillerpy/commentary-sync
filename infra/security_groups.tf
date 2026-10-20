# Who may reach what. Ingress is listed exactly; nothing is open that the
# design doesn't need.

resource "aws_security_group" "alb" {
  name        = "${var.project}-alb"
  description = "The load balancer: HTTPS from anywhere, HTTP only to redirect."
  vpc_id      = aws_vpc.main.id
}

resource "aws_vpc_security_group_ingress_rule" "alb" {
  for_each = { https = local.ports.https, http = local.ports.http }
  # checkov:skip=CKV_AWS_260:Port 80 answers only with a redirect to HTTPS (aws_lb_listener.http)

  security_group_id = aws_security_group.alb.id
  description       = "${upper(each.key)} from anywhere"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = each.value
  to_port           = each.value
}

resource "aws_vpc_security_group_egress_rule" "alb_to_tasks" {
  security_group_id            = aws_security_group.alb.id
  description                  = "To the tasks only"
  referenced_security_group_id = aws_security_group.tasks.id
  ip_protocol                  = "tcp"
  from_port                    = local.ports.web
  to_port                      = local.ports.api
}

resource "aws_security_group" "tasks" {
  name        = "${var.project}-tasks"
  description = "The Fargate tasks: reachable only from the load balancer."
  vpc_id      = aws_vpc.main.id
}

resource "aws_vpc_security_group_ingress_rule" "tasks_from_alb" {
  for_each = { api = local.ports.api, web = local.ports.web }

  security_group_id            = aws_security_group.tasks.id
  description                  = "${each.key} from the load balancer"
  referenced_security_group_id = aws_security_group.alb.id
  ip_protocol                  = "tcp"
  from_port                    = each.value
  to_port                      = each.value
}

# Out to the database (Neon), ECR, SSM, ESPN, and the LiveKit VM.
resource "aws_vpc_security_group_egress_rule" "tasks_out" {
  security_group_id = aws_security_group.tasks.id
  description       = "Anywhere: the database, AWS APIs, ESPN, the VM"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

resource "aws_security_group" "livekit" {
  name        = "${var.project}-livekit"
  description = "The LiveKit VM: media and TLS signalling from anywhere; Redis and the server API from the tasks only."
  vpc_id      = aws_vpc.main.id
}

resource "aws_vpc_security_group_ingress_rule" "livekit_public" {
  # checkov:skip=CKV_AWS_260:Port 80 is Caddy's Let's Encrypt challenge, and its redirect to HTTPS
  for_each = {
    https   = { port = local.ports.https, protocol = "tcp" }   # wss signalling, through Caddy
    acme    = { port = local.ports.http, protocol = "tcp" }    # Caddy's certificate challenge
    ice_tcp = { port = local.ports.ice_tcp, protocol = "tcp" } # WebRTC over TCP, for strict networks
    ice_udp = { port = local.ports.ice_udp, protocol = "udp" } # WebRTC media
  }

  security_group_id = aws_security_group.livekit.id
  description       = each.key
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = each.value.protocol
  from_port         = each.value.port
  to_port           = each.value.port
}

resource "aws_vpc_security_group_ingress_rule" "livekit_from_tasks" {
  for_each = { redis = local.ports.redis, server_api = local.ports.livekit_http }

  security_group_id            = aws_security_group.livekit.id
  description                  = "${each.key} from the tasks"
  referenced_security_group_id = aws_security_group.tasks.id
  ip_protocol                  = "tcp"
  from_port                    = each.value
  to_port                      = each.value
}

# Out: webhooks to the API, S3 uploads, image pulls, STUN.
resource "aws_vpc_security_group_egress_rule" "livekit_out" {
  security_group_id = aws_security_group.livekit.id
  description       = "Anywhere: webhooks, S3, image pulls, STUN"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}
