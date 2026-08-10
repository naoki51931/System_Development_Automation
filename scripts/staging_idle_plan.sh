#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
staging_root="$repo_root/environment/staging"

terraform -chdir="$staging_root" plan \
  -var-file=terraform.tfvars \
  -var='staging_mode=idle' \
  -var='enable_runtime_services=false' \
  -var='idle_database_removal_approved=false' \
  -out=staging-idle.tfplan
terraform -chdir="$staging_root" show -no-color staging-idle.tfplan

echo "REVIEW ONLY: idle_database_removal_approved=false makes this plan ineligible for apply."
