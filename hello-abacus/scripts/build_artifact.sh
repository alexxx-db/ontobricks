#!/usr/bin/env bash
# Builds app_artifact/, the directory every target deploys as the app. It holds the
# backend package, the built frontend in dist/, each backend dependency as a wheel for
# the Apps runtime (CPython 3.11 on Linux x86_64), and a requirements.txt that the Apps
# container installs with no package index. Customer workspaces block PyPI, so nothing
# the app needs may be fetched after this script runs.
#
#   bash scripts/build_artifact.sh
#
# Run it after the frontend build, which writes backend/dist/. Resolving and downloading
# need PyPI, so this runs on a machine with internet access: a laptop or CI.
set -euo pipefail

cd "$(dirname "$0")/.."

PACKAGE=backend
OUT=app_artifact
WORK="$(mktemp -d)"
trap 'rm -rf -- "$WORK"' EXIT

test -f backend/dist/index.html || { echo "backend/dist/ is missing; build the frontend first." >&2; exit 1; }

# Empty the directory but keep it: git tracks it through .gitkeep.
find "$OUT" -mindepth 1 ! -name .gitkeep -exec rm -rf -- {} +
mkdir -p "$OUT/wheels"

# The locked runtime dependencies, resolved for the Apps platform so no environment
# marker is left for the container to evaluate.
uv export --project backend --frozen --no-dev --no-emit-project --no-hashes --no-header --no-annotate \
  --output-file "$WORK/locked.txt" >/dev/null
uv pip compile "$WORK/locked.txt" --python-version 3.11 --python-platform x86_64-manylinux_2_28 \
  --no-header --no-annotate --quiet --output-file "$WORK/resolved.txt"

uvx --python 3.11 --from pip==25.3 pip download --quiet --disable-pip-version-check --no-deps \
  --only-binary=:all: --implementation cp --python-version 3.11 \
  --abi cp311 --abi abi3 --abi none \
  --platform manylinux_2_28_x86_64 --platform manylinux_2_17_x86_64 --platform manylinux2014_x86_64 --platform any \
  --dest "$OUT/wheels" --requirement "$WORK/resolved.txt"

{
  echo "--no-index"
  echo "--find-links ./wheels"
  cat "$WORK/resolved.txt"
} > "$OUT/requirements.txt"

# Source without tests or caches. config.py finds dist/ two levels above itself.
cp -R "backend/$PACKAGE" "$OUT/"
find "$OUT/$PACKAGE" \( -name __pycache__ -o -name "test_*.py" \) -prune -exec rm -rf -- {} +
cp -R backend/dist "$OUT/dist"

echo "Built $OUT/: $(find "$OUT/wheels" -name '*.whl' | wc -l | tr -d ' ') wheels."
