# Offline tests: mock AWS providers, so no credentials, no cost and nothing
# created. Each run pins a design decision that would be costly or unsafe to
# lose. Run from infra/: terraform test

mock_provider "aws" {
  # Mocks invent random strings; arguments the provider checks for ARN shape
  # get real-looking ones.
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/mock" }
  }
  mock_resource "aws_cloudwatch_log_group" {
    defaults = { arn = "arn:aws:logs:us-east-2:123456789012:log-group:mock" }
  }
  mock_resource "aws_s3_bucket" {
    defaults = { arn = "arn:aws:s3:::mock-bucket", bucket = "mock-bucket", bucket_regional_domain_name = "mock-bucket.s3.us-east-2.amazonaws.com" }
  }
  mock_resource "aws_ecr_repository" {
    defaults = { arn = "arn:aws:ecr:us-east-2:123456789012:repository/mock", repository_url = "123456789012.dkr.ecr.us-east-2.amazonaws.com/mock" }
  }
  mock_resource "aws_lb" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-east-2:123456789012:loadbalancer/app/mock/1", arn_suffix = "app/mock/1" }
  }
  mock_resource "aws_lb_target_group" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-east-2:123456789012:targetgroup/mock/1", arn_suffix = "targetgroup/mock/1" }
  }
  mock_resource "aws_lb_listener" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-east-2:123456789012:listener/app/mock/1/1" }
  }
  mock_resource "aws_ecs_task_definition" {
    defaults = { arn = "arn:aws:ecs:us-east-2:123456789012:task-definition/mock:1" }
  }
  mock_resource "aws_ecs_cluster" {
    defaults = { id = "arn:aws:ecs:us-east-2:123456789012:cluster/mock", arn = "arn:aws:ecs:us-east-2:123456789012:cluster/mock" }
  }
  mock_resource "aws_ecs_service" {
    defaults = { id = "arn:aws:ecs:us-east-2:123456789012:service/mock/mock" }
  }
  mock_resource "aws_sns_topic" {
    defaults = { arn = "arn:aws:sns:us-east-2:123456789012:mock" }
  }
  mock_resource "aws_acm_certificate" {
    defaults = {
      arn = "arn:aws:acm:us-east-1:123456789012:certificate/mock"
      domain_validation_options = [
        for host in ["api.test.example", "studio.test.example", "hls.test.example"] :
        { domain_name = host, resource_record_name = "_x.${host}.", resource_record_type = "CNAME", resource_record_value = "_y.acm-validations.aws." }
      ]
    }
  }
  mock_resource "aws_acm_certificate_validation" {
    defaults = { certificate_arn = "arn:aws:acm:us-east-1:123456789012:certificate/mock" }
  }
  mock_resource "aws_cloudfront_distribution" {
    defaults = { arn = "arn:aws:cloudfront::123456789012:distribution/MOCK", domain_name = "mock.cloudfront.net", hosted_zone_id = "Z2FDTNDATAQYW2" }
  }
  mock_resource "aws_eip" {
    defaults = { public_ip = "203.0.113.10" }
  }
  mock_resource "aws_instance" {
    defaults = { private_ip = "10.20.0.50" }
  }
  override_data {
    target = data.aws_caller_identity.current
    values = { account_id = "123456789012" }
  }
  override_data {
    target = data.aws_route53_zone.main
    values = { zone_id = "Z0000000MOCK" }
  }
  override_data {
    target = data.aws_iam_openid_connect_provider.github
    values = { arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com" }
  }
}

mock_provider "aws" {
  alias = "us_east_1"
  mock_resource "aws_acm_certificate" {
    defaults = {
      arn = "arn:aws:acm:us-east-1:123456789012:certificate/mock"
      domain_validation_options = [
        for host in ["api.test.example", "studio.test.example", "hls.test.example"] :
        { domain_name = host, resource_record_name = "_x.${host}.", resource_record_type = "CNAME", resource_record_value = "_y.acm-validations.aws." }
      ]
    }
  }
  mock_resource "aws_acm_certificate_validation" {
    defaults = { certificate_arn = "arn:aws:acm:us-east-1:123456789012:certificate/mock" }
  }
}

variables {
  domain_name = "test.example"
  alert_email = "alerts@test.example"
}

run "no_nat_gateway_tasks_reachable_only_from_the_load_balancer" {
  command = apply

  assert {
    condition     = one(aws_route_table.public.route).gateway_id == aws_internet_gateway.main.id
    error_message = "The internet route must use the free internet gateway, not a NAT gateway."
  }
  assert {
    condition     = alltrue([for rule in aws_vpc_security_group_ingress_rule.tasks_from_alb : rule.referenced_security_group_id == aws_security_group.alb.id && rule.cidr_ipv4 == null])
    error_message = "The tasks may only be reached from the load balancer's security group."
  }
  assert {
    condition     = alltrue([for service in aws_ecs_service.service : one(service.network_configuration).assign_public_ip])
    error_message = "Without a NAT gateway, tasks need public IPs to reach ECR, SSM and the database."
  }
}

run "secrets_never_in_terraform_or_the_task_definitions" {
  command = apply

  assert {
    condition     = alltrue([for parameter in aws_ssm_parameter.secret : parameter.value == "set-by-set-secrets-sh" && parameter.type == "SecureString"])
    error_message = "Terraform only creates placeholders; set-secrets.sh writes the real values."
  }
  assert {
    condition     = alltrue([for variable in jsondecode(aws_ecs_task_definition.service["api"].container_definitions)[0].environment : !can(regex("SECRET|PASSWORD|DATABASE|CACHE_URL", variable.name))])
    error_message = "No secret may be a plain environment variable."
  }
  assert {
    condition     = length(jsondecode(aws_ecs_task_definition.service["api"].container_definitions)[0].secrets) == 5
    error_message = "The API's five secrets come from SSM, injected by ECS."
  }
}

run "the_api_runs_hardened" {
  command = apply

  assert {
    condition = alltrue([
      for pair in [
        ["COMMENTARY_API_DOCS", "false"],
        ["COMMENTARY_HSTS_SECONDS", "31536000"],
        ["COMMENTARY_CORS_ORIGINS", "[\"https://studio.test.example\"]"],
        ["FORWARDED_ALLOW_IPS", "10.20.0.0/16"],
        ["COMMENTARY_LIVEKIT_API_URL", "http://10.20.0.50:7880"],
      ] : contains([for variable in jsondecode(aws_ecs_task_definition.service["api"].container_definitions)[0].environment : [variable.name, variable.value]], pair)
    ])
    error_message = "Docs off, HSTS on, CORS for the studio only, the load balancer trusted for client addresses, LiveKit over the private network."
  }
  assert {
    condition     = jsondecode(aws_ecs_task_definition.service["api"].container_definitions)[0].readonlyRootFilesystem
    error_message = "The API writes nothing to disk."
  }
}

run "exactly_one_scheduler_on_spot" {
  command = apply

  assert {
    condition     = aws_ecs_service.service["scheduler"].desired_count == 1 && aws_ecs_service.service["scheduler"].deployment_maximum_percent == 100 && aws_ecs_service.service["scheduler"].deployment_minimum_healthy_percent == 0
    error_message = "Two schedulers would import every game twice: a deploy stops the old one first."
  }
  assert {
    condition     = one(aws_ecs_service.service["scheduler"].capacity_provider_strategy).capacity_provider == "FARGATE_SPOT"
    error_message = "The scheduler runs on Spot: an interruption only delays an import."
  }
  assert {
    condition     = alltrue([for service in aws_ecs_service.service : one(service.deployment_circuit_breaker).rollback])
    error_message = "A deploy that never turns healthy must roll itself back."
  }
}

run "https_only_with_modern_tls" {
  command = apply

  assert {
    condition     = aws_lb_listener.https.ssl_policy == "ELBSecurityPolicy-TLS13-1-2-2021-06"
    error_message = "TLS 1.3 and 1.2 only."
  }
  assert {
    condition     = one(aws_lb_listener.http.default_action).type == "redirect" && one(one(aws_lb_listener.http.default_action).redirect).status_code == "HTTP_301"
    error_message = "Port 80 must only redirect to HTTPS."
  }
  assert {
    condition     = aws_lb.main.drop_invalid_header_fields
    error_message = "Malformed headers are dropped at the load balancer."
  }
  assert {
    condition     = one(one(aws_lb_listener_rule.api.condition).host_header).values == toset(["api.test.example"])
    error_message = "api.<domain> goes to the API; everything else to the studio."
  }
}

run "the_livekit_vm_is_locked_down" {
  command = apply

  assert {
    condition     = one(aws_instance.livekit.metadata_options).http_tokens == "required" && one(aws_instance.livekit.metadata_options).http_put_response_hop_limit == 1
    error_message = "IMDSv2 only, and no extra hop for containers to reach the instance's credentials."
  }
  assert {
    condition     = one(aws_instance.livekit.root_block_device).encrypted
    error_message = "The VM's disk is encrypted."
  }
  assert {
    condition     = toset([for rule in aws_vpc_security_group_ingress_rule.livekit_public : "${rule.ip_protocol}/${rule.from_port}"]) == toset(["tcp/443", "tcp/80", "tcp/7881", "udp/7882"])
    error_message = "From the internet: TLS signalling, the certificate challenge and WebRTC media only."
  }
  assert {
    condition     = alltrue([for rule in aws_vpc_security_group_ingress_rule.livekit_from_tasks : rule.referenced_security_group_id == aws_security_group.tasks.id && rule.cidr_ipv4 == null])
    error_message = "Redis and LiveKit's server API are reachable from the tasks only."
  }
}

run "recordings_are_private_temporary_and_served_over_https" {
  command = apply

  assert {
    condition     = aws_s3_bucket_public_access_block.hls.block_public_acls && aws_s3_bucket_public_access_block.hls.block_public_policy && aws_s3_bucket_public_access_block.hls.ignore_public_acls && aws_s3_bucket_public_access_block.hls.restrict_public_buckets
    error_message = "Only CloudFront reads the bucket."
  }
  assert {
    condition     = one(one(aws_s3_bucket_lifecycle_configuration.hls.rule).expiration).days == 3
    error_message = "Recordings are deleted after three days."
  }
  assert {
    condition     = one(aws_cloudfront_distribution.hls.ordered_cache_behavior).path_pattern == "*.m3u8" && one(aws_cloudfront_distribution.hls.ordered_cache_behavior).viewer_protocol_policy == "redirect-to-https"
    error_message = "Playlists have their own (uncached) behaviour, over HTTPS."
  }
  assert {
    condition     = one(aws_cloudfront_distribution.hls.viewer_certificate).minimum_protocol_version == "TLSv1.2_2021"
    error_message = "CloudFront speaks TLS 1.2 or newer."
  }
}

run "the_deploy_role_is_this_repositorys_main_branch_only" {
  command = apply

  assert {
    condition     = jsondecode(aws_iam_role.deploy.assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:sub"] == "repo:rjmillerpy/commentary-sync-private:ref:refs/heads/main"
    error_message = "Only the deploy workflow on main may assume the role: no pull request, fork or other branch."
  }
  assert {
    condition     = alltrue([for statement in jsondecode(aws_iam_role_policy.deploy.policy).Statement : !contains(flatten([statement.Action]), "*") && !anytrue([for action in flatten([statement.Action]) : endswith(action, ":*")])])
    error_message = "The deploy role names every action it may take."
  }
}

run "cost_guards" {
  command = apply

  assert {
    condition     = alltrue([for group in aws_cloudwatch_log_group.service : group.retention_in_days == 14])
    error_message = "Logs are kept two weeks."
  }
  assert {
    condition     = toset([for budget in aws_budgets_budget.monthly : budget.limit_amount]) == toset(["5", "20"])
    error_message = "Budget warnings at $5 and $20 a month."
  }
  assert {
    condition     = alltrue([for budget in aws_budgets_budget.monthly : one(budget.cost_filter).values == tolist(["user:project$commentary-sync"])])
    error_message = "The budgets count this project's tagged resources only."
  }
  assert {
    condition     = alltrue([for service in aws_ecs_service.service : service.desired_count == 1])
    error_message = "One task per service."
  }
}

run "alarms_reach_the_alert_email" {
  command = apply

  assert {
    condition     = length(aws_sns_topic_subscription.email) == 1 && aws_sns_topic_subscription.email[0].endpoint == "alerts@test.example"
    error_message = "Alarms go to the alert email."
  }
  assert {
    condition     = contains(aws_cloudwatch_metric_alarm.livekit_down.alarm_actions, "arn:aws:automate:us-east-2:ec2:recover")
    error_message = "A failed VM is recovered onto healthy hardware automatically."
  }
}

run "two_availability_zones_exactly" {
  command = plan

  variables {
    availability_zones = ["us-east-2a"]
  }
  expect_failures = [var.availability_zones]
}
