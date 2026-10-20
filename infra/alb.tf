# One load balancer for both web services, routed by host name:
# api.<domain> to the API, everything else (studio.<domain>) to the studio.
# HTTPS only: TLS 1.3 and 1.2; port 80 answers with a redirect.

resource "aws_lb" "main" {
  name                       = var.project
  load_balancer_type         = "application"
  subnets                    = aws_subnet.public[*].id
  security_groups            = [aws_security_group.alb.id]
  drop_invalid_header_fields = true
  # checkov:skip=CKV_AWS_91:Access logs cost S3 storage for traffic this small; the app logs every request
  # checkov:skip=CKV_AWS_150:Deletion protection would block `terraform destroy`, which tears this down between demos
  # checkov:skip=CKV2_AWS_28:A WAF is $5/month plus rules; the API rate-limits per client itself
  # checkov:skip=CKV2_AWS_20:Port 80 only redirects to HTTPS (aws_lb_listener.http)
}

resource "aws_lb_target_group" "service" {
  for_each = { api = local.ports.api, web = local.ports.web }

  # checkov:skip=CKV_AWS_378:TLS ends at the load balancer; inside the VPC the hop to the task is plain HTTP
  name                 = "${var.project}-${each.key}"
  port                 = each.value
  protocol             = "HTTP"
  target_type          = "ip"
  vpc_id               = aws_vpc.main.id
  deregistration_delay = 30 # in-flight requests are short; don't hold a deploy for five minutes

  health_check {
    # Liveness: a task whose database blinks shouldn't be killed for it.
    path                = each.key == "api" ? "/health/live" : "/"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 15
    matcher             = "200"
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port              = local.ports.https
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate_validation.regional.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.service["web"].arn
  }
}

resource "aws_lb_listener_rule" "api" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 10

  condition {
    host_header {
      values = [local.hosts.api]
    }
  }

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.service["api"].arn
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = local.ports.http
  protocol          = "HTTP" # checkov:skip=CKV_AWS_2:Answers only with a redirect to HTTPS

  default_action {
    type = "redirect"
    redirect {
      protocol    = "HTTPS"
      port        = tostring(local.ports.https)
      status_code = "HTTP_301"
    }
  }
}
