# One repository per image. Tags never move (IMMUTABLE), so a deployed tag
# always means the same image and a rollback is "deploy the old tag".

resource "aws_ecr_repository" "image" {
  for_each = toset(["api", "web"])

  name                 = "${var.project}-${each.key}"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256" # checkov:skip=CKV_AWS_136:AWS-managed encryption; a customer key is $1/month for nothing gained here
  }
}

resource "aws_ecr_lifecycle_policy" "keep_recent" {
  for_each = aws_ecr_repository.image

  repository = each.value.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the last 10 images: enough to roll back, little to store."
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 10 }
      action       = { type = "expire" }
    }]
  })
}
