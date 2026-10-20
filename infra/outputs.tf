output "urls" {
  description = "Where everything is, once applied."
  value = {
    api     = "https://${local.hosts.api}"
    studio  = "https://${local.hosts.studio}"
    livekit = "wss://${local.hosts.live}"
    hls     = "https://${local.hosts.hls}/hls"
  }
}

output "deploy_role_arn" {
  description = "Set as the repository variable AWS_DEPLOY_ROLE_ARN for the deploy workflow."
  value       = aws_iam_role.deploy.arn
}

output "ecr_repositories" {
  description = "Where the deploy workflow pushes the images."
  value       = { for name, repository in aws_ecr_repository.image : name => repository.repository_url }
}

output "livekit_private_ip" {
  description = "Redis and LiveKit's server API, as the tasks reach them; set-secrets.sh builds the cache URL from it."
  value       = aws_instance.livekit.private_ip
}

output "build_args" {
  description = "The studio's image is built with these (NEXT_PUBLIC_* are baked in)."
  value = {
    NEXT_PUBLIC_API_URL     = "https://${local.hosts.api}"
    NEXT_PUBLIC_LIVEKIT_URL = "wss://${local.hosts.live}"
  }
}

output "project" {
  description = "The SSM prefix's name, for set-secrets.sh."
  value       = var.project
}

output "region" {
  description = "For set-secrets.sh."
  value       = var.region
}
