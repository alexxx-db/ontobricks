#!/usr/bin/env bash
# Fetches the pinned Atlas Community binaries into bin/ for the migrate job. Run by the
# bundle's `atlas` artifact on every deploy. Serverless has no internet egress, so the
# bundle ships them. A download whose checksum differs is deleted and fails the deploy.
set -euo pipefail

cd "$(dirname "$0")/.."

VERSION=v1.3.1

sha256() {
  if command -v sha256sum >/dev/null; then sha256sum "$1"; else shasum -a 256 "$1"; fi | cut -d' ' -f1
}

mkdir -p bin
for arch in arm64 amd64; do
  case "$arch" in
    arm64) want=4be348491a34610eacd7fd38989f99a565d0c6967172e8784c7db500ec17fae7 ;;
    amd64) want=521aafcdc4c81a6aee3d553adc97633821a7cb28076ffcdf4add27add930c804 ;;
  esac
  out="bin/atlas-linux-$arch"
  if [ -f "$out" ] && [ "$(sha256 "$out")" = "$want" ]; then
    continue
  fi
  curl -fsSL -o "$out.download" "https://release.ariga.io/atlas/atlas-community-linux-$arch-$VERSION"
  got="$(sha256 "$out.download")"
  if [ "$got" != "$want" ]; then
    rm -f "$out.download"
    echo "Atlas $VERSION linux-$arch checksum mismatch: expected $want, got $got" >&2
    exit 1
  fi
  mv "$out.download" "$out"
done
