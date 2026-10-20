#!/usr/bin/env bash
# Static checks for infra/ (D16), with no AWS credentials:
#
#   infra/lint.sh
#
# tflint catches what `terraform validate` can't (invalid instance types,
# unused declarations, deprecated syntax); Checkov looks for insecure
# settings. Deliberate exceptions are inline `checkov:skip` comments with
# the reason. Needs tflint and uv.
set -euo pipefail
cd "$(dirname "$0")"

config="$PWD/.tflint.hcl"
tflint --init --config="$config" > /dev/null
echo "== tflint"
tflint --config="$config" --format compact --var domain_name=example.com

echo "== checkov"
# --no-build: wheels only, so installing the tools runs no package's build script.
uv run --project tools --locked --no-build --quiet checkov --directory . --framework terraform \
  --skip-path tools --compact --quiet

echo "All infra checks passed."
