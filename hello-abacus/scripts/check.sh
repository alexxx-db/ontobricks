#!/usr/bin/env bash
# Runs the checks that decide whether this app conforms to Hello Abacus, stopping at the
# first failure. With no argument it runs every section. CI names every section, so that
# a missing `atlas` fails there.
#
#   bash scripts/check.sh [backend] [frontend] [artifact] [deploy] [migrations]
#
# Atlas is needed only to write a migration, so with no argument a missing `atlas` skips
# the migrations section with a warning. Naming the section makes a missing `atlas` fail.
# ATLAS overrides the binary, as CI does with the one scripts/fetch_atlas.sh downloads.
set -euo pipefail

cd "$(dirname "$0")/.."

ATLAS="${ATLAS:-atlas}"

backend() {
  uv --directory backend run pytest
  uv --directory backend run lint-imports
  uv run --project backend python scripts/check_manifests.py
}

frontend() {
  pnpm --dir frontend install --frozen-lockfile
  pnpm --dir frontend run lint
  pnpm --dir frontend run test
  # The build runs tsc, the only type check.
  pnpm --dir frontend run build
}

# Needs the frontend build in backend/dist/, so it runs after frontend.
artifact() {
  bash scripts/build_artifact.sh
  bash scripts/check_artifact.sh
}

# The Seiji hooks and the CLI fetch, against stand-ins for aws, seiji, databricks and curl.
deploy() {
  bash deploy/test_hooks.sh
  bash scripts/test_fetch.sh
}

migrations() {
  "$ATLAS" migrate validate --dir file://migrations
  # Atlas prints nothing when the directory is valid.
  echo "Migrations valid."
}

if [ "$#" -eq 0 ]; then
  backend
  frontend
  artifact
  deploy
  if command -v "$ATLAS" >/dev/null; then
    migrations
  else
    echo "WARNING: $ATLAS not found, so atlas migrate validate did not run." >&2
  fi
  exit 0
fi

for section in "$@"; do
  case "$section" in
    backend | frontend | artifact | deploy | migrations) "$section" ;;
    *)
      echo "Unknown section: $section. Use backend, frontend, artifact, deploy, or migrations." >&2
      exit 2
      ;;
  esac
done
