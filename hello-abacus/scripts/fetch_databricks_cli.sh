#!/usr/bin/env bash
# Fetches the pinned Databricks CLI for Linux x86_64, the Seiji executor's platform, into
# cli/. CI publishes it with each tag and the Seiji hooks run it, so a deploy uses the CLI
# the tag was checked with, never the executor image's. A download whose checksum differs
# is deleted and fails.
set -euo pipefail

cd "$(dirname "$0")/.."

VERSION=1.16.1
WANT=441815d485d737a405a0020cf6eb5cbe60034b2f85a8b213657a1479bdccc46c

sha256() {
  if command -v sha256sum >/dev/null; then sha256sum "$1"; else shasum -a 256 "$1"; fi | cut -d' ' -f1
}

mkdir -p cli
archive="cli/databricks_cli_${VERSION}_linux_amd64.tar.gz"
curl -fsSL -o "$archive" "https://github.com/databricks/cli/releases/download/v${VERSION}/databricks_cli_${VERSION}_linux_amd64.tar.gz"
got="$(sha256 "$archive")"
if [ "$got" != "$WANT" ]; then
  rm -f "$archive"
  echo "Databricks CLI v$VERSION linux-amd64 checksum mismatch: expected $WANT, got $got" >&2
  exit 1
fi
tar -xzf "$archive" -C cli databricks
rm -f "$archive"
chmod +x cli/databricks
