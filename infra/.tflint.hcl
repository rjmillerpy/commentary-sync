# tflint (D16): catches what `terraform validate` can't, such as
# invalid instance types, unused declarations, missing descriptions and
# deprecated syntax. Run from infra/: tflint --init (once), then tflint --recursive.

plugin "terraform" {
  enabled = true
  preset  = "all"
}

# Written for reusable modules (main.tf + variables.tf + outputs.tf). These
# are root stacks split by topic (alb.tf, ecs.tf, dns.tf, ...), on purpose.
rule "terraform_standard_module_structure" {
  enabled = false
}

# Checks values against AWS's own API definitions (instance classes,
# regions, ...). Release signatures are verified by tflint --init.
plugin "aws" {
  enabled = true
  version = "0.49.0"
  source  = "github.com/terraform-linters/tflint-ruleset-aws"
}
