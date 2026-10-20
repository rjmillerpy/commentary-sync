# GitHub Actions deploys with short-lived credentials from OIDC: no stored
# key. The account has one GitHub OIDC provider (rad-shift's github-oidc
# stack made it), looked up here rather than made a second time. The role is
# trusted only by this repository's deploy branch, and can only push its two
# images and move its three services to new task definitions.

data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

resource "aws_iam_role" "deploy" {
  name                 = "${var.project}-github-deploy"
  description          = "Assumed by ${var.github_repository}@${var.deploy_branch}'s deploy workflow via OIDC."
  max_session_duration = 3600

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = data.aws_iam_openid_connect_provider.github.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = "repo:${var.github_repository}:ref:refs/heads/${var.deploy_branch}"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "deploy" {
  name = "push-images-and-deploy"
  role = aws_iam_role.deploy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "EcrLogin"
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*" # it has no resource to scope to
      },
      {
        Sid    = "PushTheseImages"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload", "ecr:PutImage", "ecr:BatchGetImage",
        ]
        Resource = [for repository in aws_ecr_repository.image : repository.arn]
      },
      {
        Sid      = "NewTaskDefinitions"
        Effect   = "Allow"
        Action   = ["ecs:DescribeTaskDefinition", "ecs:RegisterTaskDefinition"]
        Resource = "*" # task definition actions can't be scoped by ARN
      },
      {
        Sid      = "MoveTheseServices"
        Effect   = "Allow"
        Action   = ["ecs:UpdateService", "ecs:DescribeServices"]
        Resource = [for service in aws_ecs_service.service : service.id]
      },
      {
        Sid       = "HandTheTasksTheirRoles"
        Effect    = "Allow"
        Action    = "iam:PassRole"
        Resource  = [aws_iam_role.execution.arn, aws_iam_role.api_task.arn, aws_iam_role.web_task.arn]
        Condition = { StringEquals = { "iam:PassedToService" = "ecs-tasks.amazonaws.com" } }
      },
    ]
  })
}
