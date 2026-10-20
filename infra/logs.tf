# Two weeks of logs: enough to look into an incident, little to store.

resource "aws_cloudwatch_log_group" "service" {
  for_each = toset(["api", "scheduler", "web"])

  name              = "/ecs/${var.project}/${each.key}"
  retention_in_days = local.log_retention_days
  # checkov:skip=CKV_AWS_158:AWS-managed encryption; a customer key is $1/month for nothing gained here
  # checkov:skip=CKV_AWS_338:Two weeks, on purpose: a year of logs is a cost with no use yet
}

resource "aws_cloudwatch_log_group" "flow" {
  name              = "/vpc/${var.project}/rejected"
  retention_in_days = local.log_retention_days
  # checkov:skip=CKV_AWS_158:AWS-managed encryption; a customer key is $1/month for nothing gained here
  # checkov:skip=CKV_AWS_338:Two weeks, on purpose
}
