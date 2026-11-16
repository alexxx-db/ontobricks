#!/usr/bin/env bash
# Shared by deploy/create.sh and deploy/destroy.sh, the Seiji hooks. Seiji runs them with
# LABEL set, and with AIRFLOW_DEPLOYMENT=1 when Airflow deploys. Nothing here prints a
# secret. Running this file directly does nothing.

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo "deploy/lib.sh is sourced by deploy/create.sh and deploy/destroy.sh." >&2
  exit 1
fi

ARTIFACT_URI="s3://abacus-artifacts-kitchen/databricks-apps/hello-abacus"
ENABLED_WORKSPACES_KEY="hello_abacus_enabled_workspaces"
BUNDLE_TARGET="prd"

cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1

fail() {
  echo "[ERROR] $*" >&2
  exit 1
}

# Sets APP_TAG and WORKSPACES from the Luna config, which Seiji turns into tfvars.
# Exports the label's customer as BUNDLE_VAR_customer, from which the bundle names the
# app's groups. Base init sets it; it is not always LABEL: label cambia02's is cambia.
load_config() {
  local tool
  for tool in seiji aws jq; do
    command -v "$tool" >/dev/null || fail "$tool is not installed; the Seiji executor image has it."
  done
  [[ -n "${LABEL:-}" ]] || fail "LABEL is not set; Seiji sets it."
  seiji config generate tfvars --spec-path deploy/luna-config-spec.yaml
  local tfvars
  tfvars=$(find . -maxdepth 1 -name '*.auto.tfvars.json' | head -1)
  [[ -n "$tfvars" ]] || fail "Seiji wrote no *.auto.tfvars.json."
  APP_TAG=$(jq -r '.app_tag // empty' "$tfvars")
  WORKSPACES=$(jq -r --arg key "$ENABLED_WORKSPACES_KEY" '.[$key] // [] | .[]' "$tfvars")
  [[ -n "$APP_TAG" ]] || fail "app_tag is not set in the Luna config."
  [[ -n "$WORKSPACES" ]] || fail "$ENABLED_WORKSPACES_KEY lists no workspace."
  CUSTOMER=$(aws ssm get-parameter --name "/${LABEL}/config/_/customer" --with-decryption \
    --output text --query Parameter.Value) || fail "Cannot read /${LABEL}/config/_/customer; base init sets it."
  [[ -n "$CUSTOMER" ]] || fail "/${LABEL}/config/_/customer is empty; base init sets it."
  export BUNDLE_VAR_customer="$CUSTOMER"
}

# Writes a CLI profile named <LABEL>-<workspace> for each enabled workspace. Under
# Airflow the deployer service principal signs in with M2M OAuth; run by hand, the CLI
# uses your own `databricks auth login` for each profile's host.
configure_databricks() {
  local auth_type="databricks-cli" workspace url
  if [[ "${AIRFLOW_DEPLOYMENT:-}" == "1" ]]; then
    auth_type="oauth-m2m"
    local secret
    secret=$(aws secretsmanager get-secret-value --secret-id "${LABEL}/deployer_service_principal" \
      --output text --query SecretString)
    DATABRICKS_CLIENT_ID=$(jq -er .service_principal_id <<<"$secret") ||
      fail "${LABEL}/deployer_service_principal has no service_principal_id."
    DATABRICKS_CLIENT_SECRET=$(jq -er .client_secret <<<"$secret") ||
      fail "${LABEL}/deployer_service_principal has no client_secret."
    export DATABRICKS_CLIENT_ID DATABRICKS_CLIENT_SECRET
    unset secret
  fi
  DATABRICKS_CONFIG_FILE=$(mktemp)
  export DATABRICKS_CONFIG_FILE
  for workspace in $WORKSPACES; do
    url=$(aws ssm get-parameter --name "/${LABEL}/infrastructure/databricks/${workspace}/workspace_url" \
      --output text --query Parameter.Value)
    printf '[%s-%s]\nauth_type = %s\nhost      = %s\n\n' "$LABEL" "$workspace" "$auth_type" "$url" >>"$DATABRICKS_CONFIG_FILE"
  done
}

# Fetches the Databricks CLI CI published for APP_TAG and sets DATABRICKS_CLI to it. The
# executor image's own CLI is never used: a tag deploys with the CLI it was checked with.
fetch_cli() {
  local uri="${ARTIFACT_URI}/${APP_TAG}"
  aws s3 sync "${uri}/cli/" cli/ --delete
  [[ -f cli/databricks ]] || fail "No Databricks CLI is published at ${uri}/cli/; check the tag."
  chmod +x cli/databricks
  DATABRICKS_CLI="$PWD/cli/databricks"
  echo "[INFO] Using $("$DATABRICKS_CLI" --version)"
}

# Replaces app_artifact/ and bin/ with what CI published for APP_TAG. prd builds nothing:
# the bundle's prd build steps only check that these are here.
fetch_artifact() {
  local uri="${ARTIFACT_URI}/${APP_TAG}"
  aws s3 sync "${uri}/app_artifact/" app_artifact/ --delete --exclude .gitkeep
  aws s3 sync "${uri}/bin/" bin/ --delete
  [[ -f app_artifact/requirements.txt ]] || fail "Nothing is published at ${uri}/; check the tag."
}

# Runs a bundle command against one workspace, which the bundle also names its groups
# from. The app's schema goes in the workspace's default catalog, which ng-infrastructure
# names from the label and the workspace without its dashes, so nv-prd's is <label>_nvprd_catalog.
# The bundle keeps its state in each workspace, so the local copy is dropped first and the
# workspace's own state is read.
bundle_in() {
  local workspace="$1"
  shift
  export BUNDLE_VAR_workspace="$workspace"
  export BUNDLE_VAR_catalog="${LABEL}_${workspace//-/}_catalog"
  rm -rf -- ".databricks/bundle/${BUNDLE_TARGET}"
  "$DATABRICKS_CLI" bundle "$@" -t "$BUNDLE_TARGET" --profile "${LABEL}-${workspace}"
}

# Waits until the app's compute has settled in a state bundle run handles. bundle run
# starts a compute that is STOPPED, ERROR or has no status, and waits on one that is
# STARTING, but that wait fails if the compute stops instead. In any other state it
# deploys at once, which fails unless the compute is ACTIVE (bundle/run/app.go in
# databricks/cli, the same in v1.16.1 and v1.25.0). A new app's compute passes through
# STARTING and back to STOPPED, and was once UPDATING, a minute after the bundle created
# it. So the hook waits while the compute is in any other state, checking every 10
# seconds, 120 times, then stops, naming the state. Drop this once bundle run waits out a
# transient state itself: https://github.com/databricks/cli/issues/7451. APP_WAIT_TRIES
# and APP_WAIT_SECONDS exist for the hook tests.
wait_for_app_compute() {
  local workspace="$1" state="" try
  for ((try = 1; try <= ${APP_WAIT_TRIES:-120}; try++)); do
    state=$("$DATABRICKS_CLI" apps get hello-abacus -o json --profile "${LABEL}-${workspace}" |
      jq -r 'if .compute_status == null then "NONE" else .compute_status.state // "" end') ||
      fail "cannot read the app's compute status in ${workspace}"
    case "$state" in
      ACTIVE | STOPPED | ERROR | NONE)
        echo "[INFO] The app's compute in ${workspace} is ${state}; deploying the app"
        return 0
        ;;
      *)
        echo "[INFO] The app's compute in ${workspace} is ${state:-in an empty state}; waiting (${try}/${APP_WAIT_TRIES:-120})"
        ((try < ${APP_WAIT_TRIES:-120})) && sleep "${APP_WAIT_SECONDS:-10}"
        ;;
    esac
  done
  fail "the app's compute in ${workspace} is still ${state} after waiting; bundle run cannot deploy to it"
}

# Seiji passes --auto-approve when the run is approved in advance.
approve_flag() {
  case " $* " in
    *" --auto-approve "*) echo "--auto-approve" ;;
  esac
}
