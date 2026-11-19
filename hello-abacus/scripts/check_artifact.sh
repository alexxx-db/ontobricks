#!/usr/bin/env bash
# Proves app_artifact/ installs with no package index, as the Apps container installs it
# where PyPI is blocked. It checks every wheel against backend/uv.lock's hashes, then
# installs requirements.txt for the Apps platform into a throwaway directory, from inside
# the artifact so ./wheels resolves as it does there.
set -euo pipefail

cd "$(dirname "$0")/../app_artifact"

TARGET="$(mktemp -d)"
trap 'rm -rf -- "$TARGET"' EXIT

grep -qx -- "--no-index" requirements.txt || { echo "requirements.txt does not start with --no-index." >&2; exit 1; }

sha256() {
  if command -v sha256sum >/dev/null; then sha256sum "$1"; else shasum -a 256 "$1"; fi | cut -d' ' -f1
}

# pip downloads by version, so a file PyPI serves later for the same version fails here.
for wheel in wheels/*.whl; do
  grep -q "sha256:$(sha256 "$wheel")\"" ../backend/uv.lock || { echo "$wheel is not in backend/uv.lock." >&2; exit 1; }
done

uvx --python 3.11 --from pip==25.3 pip install --quiet --disable-pip-version-check --no-cache-dir \
  --only-binary=:all: --implementation cp --python-version 3.11 \
  --abi cp311 --abi abi3 --abi none \
  --platform manylinux_2_28_x86_64 --platform manylinux_2_17_x86_64 --platform manylinux2014_x86_64 --platform any \
  --target "$TARGET" --requirement requirements.txt

echo "app_artifact/ installs offline."
