#!/usr/bin/env bash
# Seiji create hook: deploys app_tag to each enabled workspace. Run it again with an
# earlier app_tag to roll back. Migrations only roll forward, so a rollback is safe only
# to a tag whose code works with the newer tables.
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

load_config
configure_databricks
fetch_cli
fetch_artifact

for workspace in $WORKSPACES; do
  echo "[INFO] Deploying ${APP_TAG} to ${workspace}"
  # shellcheck disable=SC2046 # approve_flag prints nothing or one flag.
  bundle_in "$workspace" deploy $(approve_flag "$@")
  bundle_in "$workspace" run migrate
  wait_for_app_compute "$workspace"
  bundle_in "$workspace" run web
done
