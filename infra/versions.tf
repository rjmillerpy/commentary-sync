# Phase 1.5 (roadmap D9-D17), written in $0 mode: formatted, validated, linted
# and tested offline with a mock provider, never applied until the user says
# go. See infra/README.md for what it costs once applied.

terraform {
  required_version = ">= 1.16.0, < 2.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.67.0"
    }
  }

  # State in S3: terraform init -backend-config=backend.hcl (see
  # backend.hcl.example). The offline checks run with -backend=false.
  backend "s3" {}
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      project    = var.project
      managed_by = "terraform"
    }
  }
}

# CloudFront only takes certificates from us-east-1.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = {
      project    = var.project
      managed_by = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}
