#!/usr/bin/env bash
set -euo pipefail

# This is the only supported IDLE apply entry point. It intentionally requires
# a fresh approved plan; never apply the review-only staging-idle.tfplan.
if [[ ${STAGING_IDLE_HUMAN_APPROVAL:-} != "APPROVED_REMOVE_STAGING_RUNTIME" ]]; then
  echo "Human approval token is missing." >&2
  exit 1
fi
if [[ -z ${STAGING_IDLE_MANUAL_SNAPSHOT_ID:-} ]]; then
  echo "STAGING_IDLE_MANUAL_SNAPSHOT_ID is required." >&2
  exit 1
fi

region=${AWS_REGION:-eu-west-2}
db_id=system-navigator-staging-db
cluster=system-navigator-staging-cluster
snapshot_status=$(aws rds describe-db-snapshots --region "$region" \
  --db-snapshot-identifier "$STAGING_IDLE_MANUAL_SNAPSHOT_ID" \
  --snapshot-type manual --query 'DBSnapshots[0].Status' --output text)
[[ $snapshot_status == "available" ]] || {
  echo "Manual snapshot is not available." >&2
  exit 1
}

deletion_protection=$(aws rds describe-db-instances --region "$region" \
  --db-instance-identifier "$db_id" \
  --query 'DBInstances[0].DeletionProtection' --output text)
[[ $deletion_protection == "False" ]] || {
  echo "RDS deletion protection must be disabled by a separately reviewed active-mode plan." >&2
  exit 1
}

service_count=$(aws ecs list-services --region "$region" --cluster "$cluster" \
  --query 'length(serviceArns)' --output text)
running_task_count=$(aws ecs list-tasks --region "$region" --cluster "$cluster" \
  --desired-status RUNNING --query 'length(taskArns)' --output text)
[[ $service_count == "0" && $running_task_count == "0" ]] || {
  echo "Runtime services or tasks still exist." >&2
  exit 1
}

echo "Manual pre-check still required: confirm DatabaseConnections is safely zero, no migration owner is active, and the change ticket records snapshot/restore ownership."
if [[ ${STAGING_IDLE_FINAL_CONFIRMATION:-} != "DATABASE_CONNECTIONS_ZERO_CONFIRMED" ]]; then
  echo "Final database-connections confirmation is missing." >&2
  exit 1
fi

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
staging_root="$repo_root/environment/staging"
terraform -chdir="$staging_root" plan \
  -var-file=terraform.tfvars \
  -var='staging_mode=idle' \
  -var='enable_runtime_services=false' \
  -var='idle_database_removal_approved=true' \
  -var="idle_database_snapshot_identifier=$STAGING_IDLE_MANUAL_SNAPSHOT_ID" \
  -out=staging-idle-approved.tfplan

echo "STOP: review staging-idle-approved.tfplan and obtain final apply approval."
echo "This script deliberately does not run terraform apply."
