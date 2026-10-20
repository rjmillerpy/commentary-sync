# Every secret as an SSM SecureString (standard tier: free). Terraform makes
# each with a placeholder and ignores its value from then on; set-secrets.sh
# writes the real ones straight to SSM. So no secret is in this code, a plan,
# or the state file.

resource "aws_ssm_parameter" "secret" {
  for_each = local.all_secrets

  # checkov:skip=CKV_AWS_337:Encrypted with the AWS-managed aws/ssm key; a customer key is $1/month for nothing gained here
  name        = "${local.ssm_prefix}/${each.key}"
  description = "Set by infra/set-secrets.sh, never by Terraform."
  type        = "SecureString"
  value       = "set-by-set-secrets-sh"

  lifecycle {
    ignore_changes = [value]
  }
}
