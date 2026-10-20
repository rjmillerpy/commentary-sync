#!/usr/bin/env bash
# Puts the deployment's secrets straight into SSM Parameter Store, once, after
# the first `terraform apply` (infra/README.md). Terraform made each
# parameter with a placeholder and never reads it back, so no secret passes
# through Terraform, a plan or its state.
#
#   AWS_PROFILE=... infra/set-secrets.sh
#
# Generates the auth secret, the LiveKit key pair and Redis's password; asks
# for the Neon connection string (not echoed). Rerunning it rotates the
# generated ones: restart the services and the VM afterwards.
set -euo pipefail
cd "$(dirname "$0")"

prefix="/$(terraform output -raw project 2>/dev/null || echo commentary-sync)"
region="$(terraform output -raw region 2>/dev/null || echo us-east-2)"
livekit_ip="$(terraform output -raw livekit_private_ip)"

put() {
  aws ssm put-parameter --region "$region" --type SecureString --overwrite \
    --name "$prefix/$1" --value "$2" > /dev/null
  echo "set $prefix/$1"
}
random() { openssl rand -base64 48 | tr -d '\n/+=' | cut -c1-"$1"; }

read -rsp "Neon connection string (postgresql://...): " neon_url
echo
# The API's driver is psycopg; Neon hands out a plain postgresql:// URL.
database_url="${neon_url/#postgresql:\/\//postgresql+psycopg://}"
database_url="${database_url/#postgres:\/\//postgresql+psycopg://}"

redis_password="$(random 40)"
put database-url "$database_url"
put auth-secret "$(random 64)"
put livekit-api-key "API$(random 12)"
put livekit-api-secret "$(random 48)"
put redis-password "$redis_password"
put cache-url "redis://:${redis_password}@${livekit_ip}:6379/0"
echo "Done. Restart the LiveKit VM and redeploy the services to pick them up."
