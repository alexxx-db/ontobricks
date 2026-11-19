#!/usr/bin/env bash
# Seiji destroy hook: removes the bundle from each enabled workspace. The app's Unity Catalog
# schema and its tables are deleted at once. lakebase_purge_on_delete is false in prd, so the
# Lakebase project is soft-deleted and purged with its data 7 days later.
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

load_config
configure_databricks
fetch_cli

for workspace in $WORKSPACES; do
  echo "[INFO] Destroying the bundle in ${workspace}"
  # shellcheck disable=SC2046 # approve_flag prints nothing or one flag.
  bundle_in "$workspace" destroy $(approve_flag "$@")
done
