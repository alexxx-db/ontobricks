#!/usr/bin/env bash
# Builds the offline dependency artifact for both apps, following hello-abacus's
# scripts/build_artifact.sh: every locked runtime dependency becomes a wheel for
# the Apps runtime (CPython 3.11 on Linux x86_64), so nothing is fetched from a
# package index at deploy or start time. The workspace has no PyPI egress.
#
#   bash scripts/build_artifact.sh           # rebuild only what uv.lock changed
#   bash scripts/build_artifact.sh --force   # rebuild both
#   bash scripts/build_artifact.sh --check   # verify only, no network (deploy.sh)
#
# Resolving and downloading need PyPI, so build on a machine with internet
# access (laptop or CI) and deploy from there. Outputs are gitignored and
# force-synced by databricks.yml:
#
#   vendor/                  main app. Wheels over 9 MiB are split into
#                            .partNN chunks (Apps rejects app files over 10 MB);
#                            vendor_bootstrap.py reassembles and installs them
#                            offline when the app starts.
#   src/mcp-server/vendor/   MCP app. All wheels are under the limit, so the
#                            Apps build installs them from requirements.txt
#                            (--no-index), exactly as hello-abacus does.
#
# Each holds wheels/, requirements.txt (exact pins, no markers), lock.sha256
# (the uv.lock it was built from) and sdist-built.txt.
set -euo pipefail

cd "$(dirname "$0")/.."

MODE=build
case "${1:-}" in
    "") ;;
    --force) MODE=force ;;
    --check) MODE=check ;;
    *) echo "usage: $0 [--force|--check]" >&2; exit 2 ;;
esac

MAX_BYTES=$((9 * 1024 * 1024))
HELPER=scripts/_internal/_vendor_artifact.py
PIP=(uvx --python 3.11 --from pip==25.3 pip)
PLATFORM_ARGS=(
    --only-binary=:all: --implementation cp --python-version 3.11
    --abi cp311 --abi abi3 --abi none
    --platform manylinux_2_28_x86_64 --platform manylinux_2_17_x86_64
    --platform manylinux2014_x86_64 --platform any
)

sha256() {
    if command -v sha256sum >/dev/null; then sha256sum "$1"; else shasum -a 256 "$1"; fi | cut -d' ' -f1
}

# The helper needs Python >= 3.11 (tomllib). Prefer uv's, fall back to python3.
py() {
    if command -v uv >/dev/null; then uv run --no-project --python 3.11 python "$@"; else python3 "$@"; fi
}

# build_one <project_dir> <vendor_dir> <parts|no-parts> [uv export args...]
build_one() {
    local project="$1" out="$2" parts="$3"; shift 3
    local lock="$project/uv.lock" lock_sha check_flag=""
    lock_sha="$(sha256 "$lock")"
    [[ "$parts" == no-parts ]] && check_flag=--no-parts

    if [[ -f "$out/lock.sha256" && "$(cat "$out/lock.sha256")" == "$lock_sha" && "$MODE" != force ]]; then
        echo "$out/ matches $lock; checking it."
        py "$HELPER" check "$out" "$lock" "$MAX_BYTES" ${check_flag:+"$check_flag"}
        return
    fi
    if [[ "$MODE" == check ]]; then
        echo "$out/ is missing or was built from a different $lock." >&2
        echo "Run 'make artifact' (bash scripts/build_artifact.sh) on a machine that can reach PyPI." >&2
        return 1
    fi
    command -v uv >/dev/null || { echo "uv is required to build the artifact: https://docs.astral.sh/uv/" >&2; exit 1; }

    echo "Building $out/ from $lock"
    local work
    work="$(mktemp -d)"
    # Start from an empty directory so no wheel from an older lock survives.
    rm -rf -- "$out"
    mkdir -p "$out/wheels"

    # The locked runtime dependencies, resolved for the Apps platform so no
    # environment marker is left for the container to evaluate.
    uv export --project "$project" --frozen --no-dev --no-emit-project --no-hashes --no-header --no-annotate \
        ${1+"$@"} --output-file "$work/locked.txt" >/dev/null
    uv pip compile "$work/locked.txt" --python-version 3.11 --python-platform x86_64-manylinux_2_28 \
        --no-header --no-annotate --quiet --output-file "$work/resolved.txt"

    py "$HELPER" partition "$lock" "$work/resolved.txt" "$work/binary.txt" "$work/sdist.txt"
    "${PIP[@]}" download --quiet --disable-pip-version-check --no-deps "${PLATFORM_ARGS[@]}" \
        --dest "$out/wheels" --requirement "$work/binary.txt"
    # Packages published only as an sdist (e.g. promise): build them here. The
    # check below rejects any that are not pure Python.
    : > "$out/sdist-built.txt"
    if [[ -s "$work/sdist.txt" ]]; then
        "${PIP[@]}" wheel --quiet --disable-pip-version-check --no-deps \
            --wheel-dir "$out/wheels" --requirement "$work/sdist.txt"
        sed -E 's/[=<>!~;[ ].*//' "$work/sdist.txt" > "$out/sdist-built.txt"
    fi

    cp "$work/resolved.txt" "$out/requirements.txt"
    if [[ "$parts" == parts ]]; then
        py "$HELPER" split "$out/wheels" "$MAX_BYTES"
    fi
    py "$HELPER" check "$out" "$lock" "$MAX_BYTES" ${check_flag:+"$check_flag"}
    echo "$lock_sha" > "$out/lock.sha256"
    rm -rf -- "$work"
    echo "Built $out/: $(find "$out/wheels" -name '*.whl' | wc -l | tr -d ' ') whole wheels, $(find "$out/wheels" -name '*.whl.part*' | wc -l | tr -d ' ') chunks, $(du -sh "$out" | cut -f1)."
}

# Main app: the same extras app.yaml used to pass to `uv run` (--extra lakebase).
build_one . vendor parts --extra lakebase
build_one src/mcp-server src/mcp-server/vendor no-parts
