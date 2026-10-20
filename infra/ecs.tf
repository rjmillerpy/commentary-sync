# Three Fargate services, each one task:
#  - api: the FastAPI app behind the load balancer (migrations run on start,
#    behind an advisory lock, so a rolling deploy is safe);
#  - scheduler: the same image, importing games and ending abandoned streams.
#    Exactly one may run, and on Spot (70% cheaper): an interruption only
#    delays the next import by a minute;
#  - web: the broadcaster studio.
# The deploy workflow registers new task definitions with new image tags;
# Terraform ignores that drift (`ignore_changes`) instead of reverting it.

locals {
  ecr_url = { for name, repository in aws_ecr_repository.image : name => repository.repository_url }
  cpu     = 256 # a quarter vCPU
  memory  = 512 # MiB: the API idles near 200

  api_environment = {
    COMMENTARY_LIVEKIT_URL     = "wss://${local.hosts.live}"
    COMMENTARY_LIVEKIT_API_URL = "http://${aws_instance.livekit.private_ip}:${local.ports.livekit_http}"
    COMMENTARY_HLS_BASE_URL    = "https://${local.hosts.hls}/hls"
    COMMENTARY_HLS_OUTPUT_ROOT = "hls" # S3 key prefix, as Egress uploads
    COMMENTARY_CORS_ORIGINS    = jsonencode(["https://${local.hosts.studio}"])
    COMMENTARY_API_DOCS        = "false"
    COMMENTARY_HSTS_SECONDS    = "31536000"
    COMMENTARY_LOG_FORMAT      = "json"
    # Only the load balancer may say who the client is (X-Forwarded-For);
    # without this every client shares the load balancer's rate limits.
    FORWARDED_ALLOW_IPS = var.vpc_cidr
  }

  api_container = {
    image       = "${local.ecr_url.api}:${var.api_image_tag}"
    essential   = true
    environment = [for name, value in local.api_environment : { name = name, value = value }]
    secrets = [
      for name, parameter in local.api_secrets : { name = name, valueFrom = "${local.parameter_arn}/${parameter}" }
    ]
    readonlyRootFilesystem = true
    mountPoints            = []
    volumesFrom            = []
  }
}

resource "aws_ecs_cluster" "main" {
  name = var.project
  # checkov:skip=CKV_AWS_65:Container Insights is about $3 per task a month; the load balancer's metrics and the logs do for now

  setting {
    name  = "containerInsights"
    value = "disabled" # about $3 per task a month; the load balancer's metrics and the logs do for now
  }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name       = aws_ecs_cluster.main.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]
}

resource "aws_ecs_task_definition" "service" {
  for_each = {
    api = {
      container = merge(local.api_container, {
        name         = "api"
        portMappings = [{ containerPort = local.ports.api, protocol = "tcp" }]
      })
      role = aws_iam_role.api_task.arn
    }
    scheduler = {
      container = merge(local.api_container, {
        name         = "scheduler"
        command      = ["python", "-m", "app.events.scheduler"]
        portMappings = []
      })
      role = aws_iam_role.api_task.arn
    }
    web = {
      container = {
        name                   = "web"
        image                  = "${local.ecr_url.web}:${var.web_image_tag}"
        essential              = true
        portMappings           = [{ containerPort = local.ports.web, protocol = "tcp" }]
        environment            = []
        readonlyRootFilesystem = false # Next writes its cache under .next
        mountPoints            = []
        volumesFrom            = []
      }
      role = aws_iam_role.web_task.arn
    }
  }

  family                   = "${var.project}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = local.cpu
  memory                   = local.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = each.value.role

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([merge(each.value.container, {
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.service[each.key].name
        awslogs-region        = var.region
        awslogs-stream-prefix = each.key
      }
    }
  })])
}

resource "aws_ecs_service" "service" {
  for_each = {
    # Where it runs, its load balancer port (none for the scheduler), and how a deploy replaces it.
    api       = { capacity = "FARGATE", port = local.ports.api, min = 100, max = 200 }
    web       = { capacity = "FARGATE", port = local.ports.web, min = 100, max = 200 }
    scheduler = { capacity = "FARGATE_SPOT", port = null, min = 0, max = 100 } # never two
  }

  name                               = each.key
  cluster                            = aws_ecs_cluster.main.id
  task_definition                    = aws_ecs_task_definition.service[each.key].arn
  desired_count                      = 1
  deployment_minimum_healthy_percent = each.value.min
  deployment_maximum_percent         = each.value.max
  enable_execute_command             = false
  propagate_tags                     = "SERVICE"

  capacity_provider_strategy {
    capacity_provider = each.value.capacity
    weight            = 1
  }

  # checkov:skip=CKV_AWS_333:No NAT gateway (about $33/month): tasks take public IPs, and their security group admits only the load balancer
  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = true # no NAT gateway; the security group admits only the load balancer
  }

  dynamic "load_balancer" {
    for_each = each.value.port == null ? [] : [each.value.port]
    content {
      target_group_arn = aws_lb_target_group.service[each.key].arn
      container_name   = each.key
      container_port   = load_balancer.value
    }
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true # a deploy that never turns healthy goes back by itself
  }

  lifecycle {
    ignore_changes = [task_definition] # the deploy workflow moves it
  }
}
