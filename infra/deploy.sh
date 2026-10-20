#!/usr/bin/env bash
# Moves the three ECS services to images tagged TAG (D17). Run by the deploy
# workflow after it has pushed both images; can also be run by hand.
#
#   infra/deploy.sh <tag>
#
# For each service: copy its current task definition with only the image tag
# changed, register that, point the service at it, then wait until all three
# are stable. A deploy that never turns healthy is rolled back by ECS itself
# (the circuit breaker in infra/ecs.tf). Needs the AWS CLI and jq.
set -euo pipefail

tag="${1:?usage: infra/deploy.sh <image tag>}"
cluster="${CLUSTER:-commentary-sync}"
services=(api scheduler web)

for service in "${services[@]}"; do
  current="$(aws ecs describe-services --cluster "$cluster" --services "$service" \
    --query 'services[0].taskDefinition' --output text)"
  # Only the image tag changes; the read-only fields describe-task-definition
  # adds are dropped, since register-task-definition refuses them.
  definition="$(aws ecs describe-task-definition --task-definition "$current" --query taskDefinition --output json \
    | jq --arg tag "$tag" '
        .containerDefinitions |= map(.image |= sub(":[^:]+$"; ":" + $tag))
        | del(.taskDefinitionArn, .revision, .status, .requiresAttributes, .compatibilities,
              .registeredAt, .registeredBy, .deregisteredAt)')"
  registered="$(aws ecs register-task-definition --cli-input-json "$definition" \
    --query 'taskDefinition.taskDefinitionArn' --output text)"
  aws ecs update-service --cluster "$cluster" --service "$service" --task-definition "$registered" > /dev/null
  echo "$service -> $registered"
done

echo "Waiting for the services to settle..."
aws ecs wait services-stable --cluster "$cluster" --services "${services[@]}"
echo "Deployed $tag."
