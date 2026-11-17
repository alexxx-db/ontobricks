#!/usr/bin/env python3
"""Helpers for ``scripts/build_artifact.sh`` (offline dependency artifact).

Subcommands:

  partition <uv.lock> <resolved.txt> <binary.txt> <sdist.txt>
      Split the resolved pins into those with a published wheel and those
      uv.lock knows only as an sdist (built locally into a wheel).
  split <wheels_dir> <max_bytes>
      Cut every file larger than max_bytes into ``<wheel>.partNN`` chunks.
  check <vendor_dir> <uv.lock> <max_bytes> [--no-parts]
      Prove the artifact is complete and matches the lock: every pin has a
      wheel, every downloaded wheel's sha256 is in uv.lock, sdist-built wheels
      are pure Python, and no file exceeds max_bytes. ``--no-parts`` (MCP app,
      installed by the Apps build from requirements.txt) forbids chunks.
"""

from __future__ import annotations

import hashlib
import re
import sys
import tempfile
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from vendor_bootstrap import PART_MARKER, reassemble  # noqa: E402


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _pins(requirements: Path) -> dict[str, str]:
    pins = {}
    for line in requirements.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        m = re.match(r"^([A-Za-z0-9_.\-]+)(\[[^\]]*\])?==([^\s;]+)", line)
        if not m:
            sys.exit(f"unpinned requirement in {requirements}: {line!r}")
        pins[_norm(m.group(1))] = m.group(3)
    return pins


def _lock_packages(lock: Path) -> list[dict]:
    return tomllib.loads(lock.read_text())["package"]


def partition(lock: Path, resolved: Path, binary_out: Path, sdist_out: Path) -> None:
    sdist_only = {_norm(p["name"]) for p in _lock_packages(lock) if p.get("sdist") and not p.get("wheels")}
    binary, sdist = [], []
    for line in resolved.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        name = _norm(re.split(r"[\[=<>!~; ]", line.strip(), maxsplit=1)[0])
        (sdist if name in sdist_only else binary).append(line)
    binary_out.write_text("\n".join(binary) + "\n")
    sdist_out.write_text("\n".join(sdist) + ("\n" if sdist else ""))
    print(f"  {len(binary)} wheels to download, {len(sdist)} to build from sdist"
          + (f" ({', '.join(s.split('==')[0] for s in sdist)})" if sdist else ""))


def split(wheels_dir: Path, max_bytes: int) -> None:
    for f in sorted(wheels_dir.glob("*.whl")):
        size = f.stat().st_size
        if size <= max_bytes:
            continue
        with open(f, "rb") as src:
            i = 0
            while chunk := src.read(max_bytes):
                (wheels_dir / f"{f.name[:-4]}{PART_MARKER}{i:02d}").write_bytes(chunk)
                i += 1
        f.unlink()
        print(f"  split {f.name} ({size / 1e6:.1f} MB) into {i} parts")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def check(vendor: Path, lock: Path, max_bytes: int, allow_parts: bool) -> None:
    errors: list[str] = []
    wheels_dir = vendor / "wheels"
    for f in wheels_dir.iterdir():
        if f.stat().st_size > max_bytes:
            errors.append(f"{f.name} is {f.stat().st_size / 1e6:.1f} MB, over the {max_bytes / 1e6:.1f} MB limit")
        if PART_MARKER in f.name and not allow_parts:
            errors.append(f"{f.name} is a chunk, but this app installs from requirements.txt at build time")
    sdist_built = set()
    sb = vendor / "sdist-built.txt"
    if sb.is_file():
        sdist_built = {_norm(n) for n in sb.read_text().split()}
    lock_text = lock.read_text()
    pins = _pins(vendor / "requirements.txt")
    with tempfile.TemporaryDirectory() as tmp:
        whole = Path(tmp)
        reassemble(wheels_dir, whole)
        found: dict[str, str] = {}
        for w in whole.glob("*.whl"):
            dist, version = w.name.split("-")[:2]
            found[_norm(dist)] = version
            if _norm(dist) in sdist_built:
                if not w.name.endswith("-none-any.whl"):
                    errors.append(f"{w.name} was built from an sdist but is not pure Python")
            elif f'sha256:{_sha256(w)}"' not in lock_text:
                errors.append(f"{w.name} does not match any hash in {lock.name}")
    for name, version in pins.items():
        if name not in found:
            errors.append(f"no wheel for {name}=={version}")
    if errors:
        print("artifact check FAILED:", *errors, sep="\n  ", file=sys.stderr)
        sys.exit(1)
    print(f"  {vendor}: {len(pins)} pins, all wheels present and matching {lock.name}")


def main(argv: list[str]) -> None:
    if not argv:
        sys.exit(__doc__)
    cmd, args = argv[0], argv[1:]
    if cmd == "partition" and len(args) == 4:
        partition(*map(Path, args))
    elif cmd == "split" and len(args) == 2:
        split(Path(args[0]), int(args[1]))
    elif cmd == "check" and len(args) in (3, 4):
        check(Path(args[0]), Path(args[1]), int(args[2]), allow_parts="--no-parts" not in args[3:])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
