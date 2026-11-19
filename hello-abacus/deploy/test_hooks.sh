#!/usr/bin/env bash
# Tests the Seiji hooks without Seiji, AWS or a workspace. Stand-ins for aws, seiji and
# the published Databricks CLI record each call, and the tests check what ran, in what order, and that a
# failure stops the hook. Run it from the project root: bash deploy/test_hooks.sh
# check() evaluates its condition after the hook runs, so conditions are single-quoted on
# purpose and read variables shellcheck cannot see being used.
# shellcheck disable=SC2016,SC2034
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FAILURES=0

# A scratch copy of the project with stand-ins first on PATH. $1 is the tfvars JSON
# Seiji would write; the label is acme and its customer acmeco, as cambia02's is cambia;
# NO_CUSTOMER makes the label's customer parameter missing; FAIL_ON makes the databricks
# stand-in fail on that subcommand;
# EMPTY_S3 makes the s3 sync stand-in publish nothing to that directory. A test may
# overwrite $WORK/secret.json, the deployer secret, after setup, and write
# $WORK/compute_states, one state a line, which apps get reports in turn, repeating the
# last, NONE meaning no compute status at all; with no file it reports ACTIVE.
setup() {
  WORK="$(mktemp -d)"
  mkdir -p "$WORK/project/deploy" "$WORK/stubs"
  cp "$ROOT"/deploy/*.sh "$ROOT"/deploy/*.yaml "$WORK/project/deploy/"
  LOG="$WORK/calls.log"
  : >"$LOG"
  printf '%s' "$1" >"$WORK/tfvars.json"
  printf '%s' '{"service_principal_id":"sp-id","client_secret":"sp-secret"}' >"$WORK/secret.json"

  cat >"$WORK/stubs/seiji" <<STUB
#!/usr/bin/env bash
echo "seiji \$*" >>"$LOG"
cp "$WORK/tfvars.json" ./package.auto.tfvars.json
STUB
  cat >"$WORK/stubs/aws" <<STUB
#!/usr/bin/env bash
echo "aws \$*" >>"$LOG"
case "\$1 \$2" in
  "secretsmanager get-secret-value") cat "$WORK/secret.json" ;;
  "ssm get-parameter") case "\$*" in
      *"--name /acme/config/_/customer "*) [[ -n "\${NO_CUSTOMER:-}" ]] && exit 254; echo acmeco ;;
      *) echo "https://\$(echo "\$*" | sed -E 's|.*/databricks/([^/]+)/.*|\1|').example.com" ;;
    esac ;;
  "s3 sync") mkdir -p "\$4"
    [[ "\$4" == "\${EMPTY_S3:-}" ]] && exit 0
    case "\$4" in
      app_artifact/) touch app_artifact/requirements.txt ;;
      cli/) cp "$WORK/published-cli" cli/databricks ;;
    esac ;;
esac
STUB
  # The image's CLI: the hooks must never run it.
  cat >"$WORK/stubs/databricks" <<STUB
#!/usr/bin/env bash
echo "image databricks \$*" >>"$LOG"
exit 1
STUB
  # The CLI published with the tag, which the s3 sync stand-in copies into cli/. S3 does
  # not keep the executable bit, so it arrives without one and the hook must add it.
  cat >"$WORK/published-cli" <<STUB
#!/usr/bin/env bash
if [[ "\$1" == --version ]]; then echo "Databricks CLI v1.16.1"; exit 0; fi
echo "databricks \$*" >>"$LOG"
echo "vars \${BUNDLE_VAR_catalog:-} \${BUNDLE_VAR_customer:-} \${BUNDLE_VAR_workspace:-}" >>"$LOG"
args="\$*"
profile="\${args##*--profile }"
workspace="\${profile#acme-}"
if grep -A2 -x "\[\$profile\]" "\$DATABRICKS_CONFIG_FILE" | tr -d ' ' | tr '\n' ' ' |
  grep -q "auth_type=oauth-m2m host=https://\$workspace.example.com" && [[ "\$DATABRICKS_CLIENT_ID" == sp-id ]]; then
  echo "signed in as sp-id to \$workspace" >>"$LOG"
fi
if [[ -n "\${FAIL_ON:-}" && "\$*" == *"\${FAIL_ON}"* ]]; then exit 1; fi
if [[ "\$1 \$2" == "apps get" ]]; then
  state=\$(head -1 "$WORK/compute_states" 2>/dev/null || true)
  [[ \$(wc -l <"$WORK/compute_states" 2>/dev/null || echo 0) -gt 1 ]] && sed -i.bak 1d "$WORK/compute_states"
  if [[ "\$state" == NONE ]]; then echo "{}"; else echo "{\\"compute_status\\":{\\"state\\":\\"\${state:-ACTIVE}\\"}}"; fi
fi
STUB
  chmod +x "$WORK/stubs/"*
  chmod -x "$WORK/published-cli"
}

# Runs a hook and records its exit status in STATUS, so a failing hook is reported by the
# checks, with its output, rather than ending this script.
run_hook() {
  STATUS=0
  (cd "$WORK/project" && PATH="$WORK/stubs:$PATH" LABEL=acme AIRFLOW_DEPLOYMENT=1 bash "deploy/$1" "${@:2}") \
    >"$WORK/out.log" 2>&1 || STATUS=$?
}

check() {
  if eval "$2"; then
    echo "ok   $1"
  else
    echo "FAIL $1"
    sed 's/^/     /' "$LOG" "$WORK/out.log"
    FAILURES=$((FAILURES + 1))
  fi
}

calls() { grep -E '^databricks (bundle|apps)' "$LOG" | sed -E 's/( -t prd)? --profile / @/'; }

TWO='{"app_tag":"26.11.1","hello_abacus_enabled_workspaces":["ws-a","ws-b"]}'

setup "$TWO"
run_hook create.sh --auto-approve
check "create deploys, migrates, checks the app's compute and deploys the app in each workspace, in order" \
  '[ $STATUS = 0 ] && [ "$(calls)" = "$(printf "%s\n" \
    "databricks bundle deploy --auto-approve @acme-ws-a" \
    "databricks bundle run migrate @acme-ws-a" \
    "databricks apps get hello-abacus -o json @acme-ws-a" \
    "databricks bundle run web @acme-ws-a" \
    "databricks bundle deploy --auto-approve @acme-ws-b" \
    "databricks bundle run migrate @acme-ws-b" \
    "databricks apps get hello-abacus -o json @acme-ws-b" \
    "databricks bundle run web @acme-ws-b")" ]'
check "create fetches the tag's artifact, Atlas binaries and Databricks CLI" \
  'grep -q "s3 sync s3://abacus-artifacts-kitchen/databricks-apps/hello-abacus/26.11.1/app_artifact/ app_artifact/" "$LOG" &&
   grep -q "s3 sync s3://abacus-artifacts-kitchen/databricks-apps/hello-abacus/26.11.1/bin/ bin/" "$LOG" &&
   grep -q "s3 sync s3://abacus-artifacts-kitchen/databricks-apps/hello-abacus/26.11.1/cli/ cli/" "$LOG"'
check "create runs the tag's CLI, never the image's" \
  'grep -q "Using Databricks CLI v1.16.1" "$WORK/out.log" && ! grep -q "^image databricks" "$LOG"'
check "every bundle call signs in as the deployer, to that workspace's host" \
  '[ "$(grep -c "^signed in as sp-id to ws-a" "$LOG")" = 4 ] && [ "$(grep -c "^signed in as sp-id to ws-b" "$LOG")" = 4 ]'
check "no secret reaches the output" '! grep -q "sp-secret" "$WORK/out.log"'
check "every bundle call gets its workspace's default catalog, the label's customer and its own workspace" \
  '[ "$(grep -c "^vars acme_wsa_catalog acmeco ws-a$" "$LOG")" = 4 ] && [ "$(grep -c "^vars acme_wsb_catalog acmeco ws-b$" "$LOG")" = 4 ]'

setup "$TWO"
FAIL_ON="run migrate" run_hook create.sh
check "a failed migrate stops before the app starts or the next workspace" \
  '[ $STATUS != 0 ] && [ "$(calls | tail -1)" = "databricks bundle run migrate @acme-ws-a" ]'

setup "$TWO"
printf '%s\n' UPDATING UPDATING ACTIVE >"$WORK/compute_states"
APP_WAIT_SECONDS=0 run_hook create.sh
check "create waits while a new app's compute is UPDATING, saying so, then deploys the app" \
  '[ $STATUS = 0 ] && [ "$(grep -c "compute in ws-a is UPDATING; waiting" "$WORK/out.log")" = 2 ] &&
   grep -q "compute in ws-a is ACTIVE; deploying the app" "$WORK/out.log" &&
   [ "$(calls | sed -n 3,6p)" = "$(printf "%s\n" \
    "databricks apps get hello-abacus -o json @acme-ws-a" \
    "databricks apps get hello-abacus -o json @acme-ws-a" \
    "databricks apps get hello-abacus -o json @acme-ws-a" \
    "databricks bundle run web @acme-ws-a")" ]'

setup "$TWO"
printf '%s\n' STARTING STOPPED >"$WORK/compute_states"
APP_WAIT_SECONDS=0 run_hook create.sh
check "create waits while a new app's compute is STARTING, and deploys once it settles at STOPPED" \
  '[ $STATUS = 0 ] && grep -q "compute in ws-a is STARTING; waiting" "$WORK/out.log" &&
   grep -q "compute in ws-a is STOPPED; deploying the app" "$WORK/out.log" &&
   [ "$(calls | sed -n 3,5p)" = "$(printf "%s\n" \
    "databricks apps get hello-abacus -o json @acme-ws-a" \
    "databricks apps get hello-abacus -o json @acme-ws-a" \
    "databricks bundle run web @acme-ws-a")" ]'

for settled in ERROR NONE; do
  setup "$TWO"
  echo "$settled" >"$WORK/compute_states"
  APP_WAIT_SECONDS=0 APP_WAIT_TRIES=2 run_hook create.sh
  check "create deploys the app at once when its compute is $settled, which bundle run starts" \
    '[ $STATUS = 0 ] && grep -q "compute in ws-a is $settled; deploying the app" "$WORK/out.log" &&
     [ "$(grep -c "^databricks apps get" "$LOG")" = 2 ]'
done

setup "$TWO"
echo SOME_NEW_STATE >"$WORK/compute_states"
APP_WAIT_SECONDS=0 APP_WAIT_TRIES=2 run_hook create.sh
check "a compute in a state the hook does not know waits, then stops, naming the state" \
  '[ $STATUS != 0 ] && grep -q "is still SOME_NEW_STATE after waiting" "$WORK/out.log" &&
   ! grep -q "^databricks bundle run web" "$LOG"'

setup "$TWO"
echo UPDATING >"$WORK/compute_states"
APP_WAIT_SECONDS=0 APP_WAIT_TRIES=3 run_hook create.sh
check "a compute still UPDATING after the wait stops before the app deploys, naming the state" \
  '[ $STATUS != 0 ] && grep -q "is still UPDATING after waiting" "$WORK/out.log" &&
   [ "$(calls | tail -1)" = "databricks apps get hello-abacus -o json @acme-ws-a" ]'

setup "$TWO"
FAIL_ON="apps get" APP_WAIT_SECONDS=0 APP_WAIT_TRIES=2 run_hook create.sh
check "a failed compute check stops before the app deploys or the next workspace, naming the step" \
  '[ $STATUS != 0 ] && grep -q "cannot read the app.s compute status in ws-a" "$WORK/out.log" && [ "$(calls | tail -1)" = "databricks apps get hello-abacus -o json @acme-ws-a" ]'

setup '{"hello_abacus_enabled_workspaces":["ws-a"]}'
run_hook create.sh
check "create refuses to run without app_tag" '[ $STATUS != 0 ] && grep -q "app_tag is not set" "$WORK/out.log" && [ -z "$(calls)" ]'

setup "$TWO"
run_hook destroy.sh
check "destroy removes the bundle from each workspace with the tag's CLI, waiting for approval" \
  '[ $STATUS = 0 ] && [ "$(calls)" = "$(printf "%s\n" "databricks bundle destroy @acme-ws-a" "databricks bundle destroy @acme-ws-b")" ] &&
   ! grep -q "^image databricks" "$LOG"'

setup "$TWO"
FAIL_ON="bundle destroy" run_hook destroy.sh --auto-approve
check "a failed destroy stops before the next workspace" \
  '[ $STATUS != 0 ] && [ "$(calls)" = "databricks bundle destroy --auto-approve @acme-ws-a" ]'

setup "$TWO"
run_hook create.sh
check "create passes --auto-approve to the bundle only when Seiji passes it" \
  '[ $STATUS = 0 ] && [ "$(calls | grep "bundle deploy")" = "$(printf "%s\n" \
    "databricks bundle deploy @acme-ws-a" "databricks bundle deploy @acme-ws-b")" ]'

setup '{"app_tag":"26.11.1"}'
run_hook create.sh
check "create refuses to run with no enabled workspace" \
  '[ $STATUS != 0 ] && grep -q "lists no workspace" "$WORK/out.log" && [ -z "$(calls)" ]'

setup "$TWO"
printf '%s' '{"client_secret":"sp-secret"}' >"$WORK/secret.json"
run_hook create.sh
check "a deployer secret without service_principal_id stops, naming the secret" \
  '[ $STATUS != 0 ] && grep -q "acme/deployer_service_principal has no service_principal_id" "$WORK/out.log" &&
   [ -z "$(calls)" ] && ! grep -q "sp-secret" "$WORK/out.log"'

setup "$TWO"
NO_CUSTOMER=1 run_hook create.sh
check "create refuses to run when the label has no customer, naming its parameter" \
  '[ $STATUS != 0 ] && grep -q "Cannot read /acme/config/_/customer" "$WORK/out.log" && [ -z "$(calls)" ]'

setup "$TWO"
EMPTY_S3=cli/ run_hook create.sh
check "create stops when the tag has no published CLI" \
  '[ $STATUS != 0 ] && grep -q "No Databricks CLI is published" "$WORK/out.log" && [ -z "$(calls)" ]'

setup "$TWO"
EMPTY_S3=app_artifact/ run_hook create.sh
check "create stops when the tag has no published artifact" \
  '[ $STATUS != 0 ] && grep -q "Nothing is published" "$WORK/out.log" && [ -z "$(calls)" ]'

if [ "$FAILURES" -gt 0 ]; then
  echo "$FAILURES hook test(s) failed." >&2
  exit 1
fi
echo "Hook tests passed."
