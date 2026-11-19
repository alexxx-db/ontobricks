#!/usr/bin/env bash
# Tests scripts/fetch_databricks_cli.sh without the network. A curl stand-in serves a
# file that is not the pinned release, and the script must fail, name the mismatch and
# delete the download. CI's checks job fetches the real release, which proves the pin.
# Run it from the project root: bash scripts/test_fetch.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf -- "$WORK"' EXIT

mkdir -p "$WORK/project/scripts" "$WORK/stubs"
cp "$ROOT/scripts/fetch_databricks_cli.sh" "$WORK/project/scripts/"
cat >"$WORK/stubs/curl" <<'STUB'
#!/usr/bin/env bash
while [ "$#" -gt 0 ]; do
  if [ "$1" = "-o" ]; then echo "not the release" >"$2"; exit 0; fi
  shift
done
exit 1
STUB
chmod +x "$WORK/stubs/curl"

STATUS=0
(cd "$WORK/project" && PATH="$WORK/stubs:$PATH" bash scripts/fetch_databricks_cli.sh) >"$WORK/out.log" 2>&1 || STATUS=$?

if [ "$STATUS" != 0 ] && grep -q "checksum mismatch" "$WORK/out.log" && [ -z "$(ls -A "$WORK/project/cli")" ]; then
  echo "ok   a download whose checksum differs fails and is deleted"
else
  echo "FAIL a download whose checksum differs fails and is deleted"
  sed 's/^/     /' "$WORK/out.log"
  exit 1
fi
echo "Fetch tests passed."
