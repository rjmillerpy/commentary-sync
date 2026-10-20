# Each role does one job and can do nothing else.
#  - execution role: ECS itself pulls images, writes logs and reads the
#    secrets it injects. The app never holds these permissions.
#  - task role: the app's own code. The API needs no AWS permission at all
#    (it calls LiveKit, not S3), so its task role has none.
#  - the VM's role: read its three secrets, write HLS into the bucket, and
#    be reached by Session Manager instead of SSH.

locals {
  ecs_trust = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = { StringEquals = { "aws:SourceAccount" = local.account_id } }
    }]
  })
  parameter_arn = "arn:aws:ssm:${var.region}:${local.account_id}:parameter${local.ssm_prefix}"
}

resource "aws_iam_role" "execution" {
  name               = "${var.project}-task-execution"
  assume_role_policy = local.ecs_trust
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "execution_secrets" {
  name = "read-api-secrets"
  role = aws_iam_role.execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "TheApisParametersOnly"
      Effect   = "Allow"
      Action   = ["ssm:GetParameters"]
      Resource = [for name in values(local.api_secrets) : "${local.parameter_arn}/${name}"]
    }]
  })
}

resource "aws_iam_role" "api_task" {
  name               = "${var.project}-api-task"
  description        = "The API's and scheduler's code: no AWS permissions."
  assume_role_policy = local.ecs_trust
}

resource "aws_iam_role" "web_task" {
  name               = "${var.project}-web-task"
  description        = "The studio's server: no AWS permissions."
  assume_role_policy = local.ecs_trust
}

resource "aws_iam_role" "livekit" {
  name = "${var.project}-livekit-vm"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "livekit_session_manager" {
  role       = aws_iam_role.livekit.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "livekit" {
  name = "secrets-and-hls"
  role = aws_iam_role.livekit.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ItsOwnSecretsOnly"
        Effect   = "Allow"
        Action   = ["ssm:GetParameter"]
        Resource = [for name in local.livekit_secrets : "${local.parameter_arn}/${name}"]
      },
      {
        Sid      = "WriteHlsOnly"
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = "${aws_s3_bucket.hls.arn}/hls/*"
      },
    ]
  })
}

resource "aws_iam_instance_profile" "livekit" {
  name = "${var.project}-livekit-vm"
  role = aws_iam_role.livekit.name
}

resource "aws_iam_role" "flow_logs" {
  name = "${var.project}-flow-logs"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "vpc-flow-logs.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = { StringEquals = { "aws:SourceAccount" = local.account_id } }
    }]
  })
}

resource "aws_iam_role_policy" "flow_logs" {
  name = "write-flow-log"
  role = aws_iam_role.flow_logs.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"]
      Resource = "${aws_cloudwatch_log_group.flow.arn}:*"
    }]
  })
}
