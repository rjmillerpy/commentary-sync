# Alarms and budgets, to an email. A budget can't stop spending, only say so:
# the README's teardown is the stop.

resource "aws_sns_topic" "alerts" {
  name              = "${var.project}-alerts"
  kms_master_key_id = "alias/aws/sns"
}

resource "aws_sns_topic_subscription" "email" {
  count = var.alert_email == "" ? 0 : 1

  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_cloudwatch_metric_alarm" "api_error_rate" {
  alarm_name          = "${var.project}-api-5xx-rate"
  alarm_description   = "More than 5% of API requests failed (5xx) for 5 minutes."
  comparison_operator = "GreaterThanThreshold"
  threshold           = 5
  evaluation_periods  = 5
  datapoints_to_alarm = 5
  treat_missing_data  = "notBreaching" # no traffic isn't an outage
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]

  metric_query {
    id          = "rate"
    expression  = "100 * errors / MAX([errors, requests])"
    label       = "5xx %"
    return_data = true
  }

  dynamic "metric_query" {
    for_each = { errors = "HTTPCode_Target_5XX_Count", requests = "RequestCount" }
    content {
      id = metric_query.key
      metric {
        namespace   = "AWS/ApplicationELB"
        metric_name = metric_query.value
        period      = 60
        stat        = "Sum"
        dimensions = {
          LoadBalancer = aws_lb.main.arn_suffix
          TargetGroup  = aws_lb_target_group.service["api"].arn_suffix
        }
      }
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "api_unhealthy" {
  alarm_name          = "${var.project}-api-unhealthy"
  alarm_description   = "No healthy API task for 5 minutes."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HealthyHostCount"
  statistic           = "Minimum"
  period              = 60
  evaluation_periods  = 5
  comparison_operator = "LessThanThreshold"
  threshold           = 1
  treat_missing_data  = "breaching" # no health data at all means it's down
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
  dimensions = {
    LoadBalancer = aws_lb.main.arn_suffix
    TargetGroup  = aws_lb_target_group.service["api"].arn_suffix
  }
}

# The VM failing its status checks: the hardware or the OS. EC2 recovers the
# instance onto healthy hardware by itself.
resource "aws_cloudwatch_metric_alarm" "livekit_down" {
  alarm_name          = "${var.project}-livekit-status"
  alarm_description   = "The LiveKit VM failed its status checks; EC2 is recovering it."
  namespace           = "AWS/EC2"
  metric_name         = "StatusCheckFailed_System"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  alarm_actions       = [aws_sns_topic.alerts.arn, "arn:aws:automate:${var.region}:ec2:recover"]
  dimensions          = { InstanceId = aws_instance.livekit.id }
}

# This project's spending only: resources carry `project` (default_tags),
# which must be activated once as a cost allocation tag (README).
resource "aws_budgets_budget" "monthly" {
  for_each = { for threshold in var.budget_thresholds_usd : tostring(threshold) => threshold }

  name         = "${var.project}-${each.key}-usd"
  budget_type  = "COST"
  limit_amount = tostring(each.value)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "TagKeyValue"
    values = [format("user:project$%s", var.project)] # AWS writes tag filters as key$value
  }

  dynamic "notification" {
    for_each = var.alert_email == "" ? [] : ["ACTUAL", "FORECASTED"]
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = 100
      threshold_type             = "PERCENTAGE"
      notification_type          = notification.value
      subscriber_email_addresses = [var.alert_email]
    }
  }
}
