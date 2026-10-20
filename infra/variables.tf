variable "project" {
  description = "Name prefix for every resource, and the `project` tag the budget filters on."
  type        = string
  default     = "commentary-sync"
}

variable "region" {
  description = "Where everything but CloudFront's certificate lives. us-east-2 matches the account's other project."
  type        = string
  default     = "us-east-2"
}

variable "domain_name" {
  description = "The registered domain; its Route 53 hosted zone must already exist (registering one creates it). Sub-domains: api, studio, live, hls."
  type        = string
}

variable "availability_zones" {
  description = "The two zones the load balancer spans, named so the set can't change under the stack."
  type        = list(string)
  default     = ["us-east-2a", "us-east-2b"]

  validation {
    condition     = length(var.availability_zones) == 2
    error_message = "The load balancer needs exactly two zones here."
  }
}

variable "vpc_cidr" {
  description = "The VPC's address range. Its own load balancer is the only proxy the API trusts for client addresses."
  type        = string
  default     = "10.20.0.0/16"
}

variable "api_image_tag" {
  description = "The API image's tag in ECR to start with; the deploy workflow moves services to new tags after that."
  type        = string
  default     = "initial"
}

variable "web_image_tag" {
  description = "The studio image's tag in ECR to start with."
  type        = string
  default     = "initial"
}

variable "livekit_instance_type" {
  description = "The VM running LiveKit, Egress (HLS recording), Redis and Caddy. WebRTC needs UDP and a public IP, which Fargate behind a load balancer can't give."
  type        = string
  default     = "t3a.small"
}

variable "github_repository" {
  description = "owner/name of the repository whose deploy workflow may assume the deploy role: the private one; the public mirror never deploys."
  type        = string
  default     = "rjmillerpy/commentary-sync-private"
}

variable "deploy_branch" {
  description = "The only branch the deploy role trusts."
  type        = string
  default     = "main"
}

variable "alert_email" {
  description = "Where alarms and budget warnings go. Empty: alarms are created but nobody is told."
  type        = string
  default     = ""
}

variable "budget_thresholds_usd" {
  description = "Monthly cost (USD, this project's tagged resources) at which to email: a warning and a stop-and-look."
  type        = list(number)
  default     = [5, 20]
}

variable "hls_retention_days" {
  description = "How long recorded HLS segments are kept in S3. Listeners only play within minutes; storage is billed."
  type        = number
  default     = 3
}
