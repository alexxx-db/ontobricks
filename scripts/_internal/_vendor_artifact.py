#!/usr/bin/env python3
"""Helpers for ``scripts/build_artifact.sh`` (offline dependency artifact).

Subcommands:

  partition <uv.lock> <resolved.txt> <binary.txt> <sdist.txt>
      Split the resolved pins into those with a published wheel and those
      uv.lock knows only as an sdist (built locally into a wheel).
  download <uv.lock> <binary.txt> <wheels_dir>
      Download each pinned wheel straight from the URL recorded in uv.lock,
      verifying sha256. No package index is contacted, so this works where
      pypi.org is unreachable but files.pythonhosted.org is not.
  fetch-sdists <uv.lock> <sdist.txt> <sdists_dir>
      Same for sdist-only pins, so they can be wheeled locally.
  prune <locked.txt> <resolved.txt>
      Evaluate the environment markers in a uv export against the fixed Apps
      runtime (CPython 3.11, Linux, x86_64) and write the surviving pins
      without markers. Offline replacement for `uv pip compile`, which
      contacts the index even though every pin is locked.
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


# Marker environment of the Databricks Apps runtime: CPython 3.11 on Linux
# x86_64. Keys follow PEP 508.
_TARGET_ENV = {
    "implementation_name": "cpython",
    "implementation_version": "3.11.14",
    "os_name": "posix",
    "platform_machine": "x86_64",
    "platform_python_implementation": "CPython",
    "platform_release": "",
    "platform_system": "Linux",
    "platform_version": "",
    "python_full_version": "3.11.14",
    "python_version": "3.11",
    "sys_platform": "linux",
    "extra": "",
}
_VERSION_KEYS = {"python_version", "python_full_version", "implementation_version"}
_CMP = re.compile(r"([a-z_]+)\s*(not\s+in|in|==|!=|===|<=|>=|<|>)\s*(['\"])(.*?)\3")


def _vkey(v: str) -> tuple[int, ...]:
    nums = tuple(int(p) for p in re.findall(r"\d+", v))
    return nums + (0,) * (4 - len(nums))


def _cmp(left: str, op: str, right: str, version: bool) -> bool:
    if op == "in":
        return left in right
    if op == "not in":
        return left not in right
    a, b = (_vkey(left), _vkey(right)) if version else (left, right)
    return {"==": a == b, "===": a == b, "!=": a != b, "<": a < b,
            "<=": a <= b, ">": a > b, ">=": a >= b}[op]


def _marker_ok(marker: str) -> bool:
    def repl(m: re.Match) -> str:
        return str(_cmp(_TARGET_ENV[m.group(1)], m.group(2).replace(" ", ""), m.group(4),
                        m.group(1) in _VERSION_KEYS))
    expr = _CMP.sub(repl, marker)
    if re.search(r"[^TrueFalsednort()\s]", expr):
        sys.exit(f"cannot evaluate marker: {marker!r}")
    return bool(eval(expr, {"__builtins__": {}}))


def prune(locked: Path, resolved: Path) -> None:
    kept = []
    for line in locked.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "-")):
            continue
        req, _, marker = line.partition(";")
        if marker.strip() and not _marker_ok(marker.strip()):
            continue
        kept.append(req.strip())
    resolved.write_text("\n".join(kept) + "\n")
    print(f"  {len(kept)} pins after evaluating markers for CPython 3.11 / linux x86_64")


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


def _wheel_score(fname: str) -> int | None:
    """Score a wheel filename for the Apps platform (CPython 3.11, glibc <= 2.28,
    x86_64), mirroring PLATFORM_ARGS in build_artifact.sh. Higher is more
    specific; None means incompatible."""
    stem = fname[:-4].split("-")
    py_tags, abi_tags, plat_tags = (t.split(".") for t in stem[-3:])
    py_score = None
    for t in py_tags:
        if t in ("py3", *(f"py3{n}" for n in range(12))):
            py_score = max(py_score or 0, 1)
        elif t == "cp311":
            py_score = max(py_score or 0, 3)
        elif re.fullmatch(r"cp3([0-9]|10|11)", t):
            py_score = max(py_score or 0, 2)
    if py_score is None:
        return None
    abi_ok = any(
        a == "none"
        or (a == "abi3" and any(t.startswith("cp3") for t in py_tags))
        or (a == "cp311" and "cp311" in py_tags)
        for a in abi_tags
    )
    if not abi_ok:
        return None
    plat_score = None
    for t in plat_tags:
        if t == "any":
            plat_score = max(plat_score or 0, 0)
        elif t in ("manylinux1_x86_64", "manylinux2010_x86_64", "manylinux2014_x86_64"):
            plat_score = max(plat_score or 0, 1)
        elif t == "manylinux_2_28_x86_64":
            plat_score = max(plat_score or 0, 3)
        elif m := re.fullmatch(r"manylinux_2_(\d+)_x86_64", t):
            if int(m.group(1)) <= 28:
                plat_score = max(plat_score or 0, 2)
    if plat_score is None:
        return None
    return plat_score * 10 + py_score


def _fetch(url: str, dest: Path, want_sha256: str) -> None:
    import urllib.request
    with urllib.request.urlopen(url, timeout=60) as resp, open(dest, "wb") as f:
        h = hashlib.sha256()
        while block := resp.read(1 << 20):
            h.update(block)
            f.write(block)
    if h.hexdigest() != want_sha256:
        dest.unlink()
        sys.exit(f"{dest.name}: sha256 {h.hexdigest()} != lock {want_sha256}")


def download(lock: Path, binary: Path, wheels_dir: Path) -> None:
    pkgs = {_norm(p["name"]): p for p in _lock_packages(lock)}
    wheels_dir.mkdir(parents=True, exist_ok=True)
    for name, version in sorted(_pins(binary).items()):
        pkg = pkgs.get(name)
        best = max(
            ((s, w) for w in (pkg or {}).get("wheels", [])
             if (s := _wheel_score(w["url"].rsplit("/", 1)[-1])) is not None),
            default=None,
        )
        if best is None:
            sys.exit(f"no platform-compatible wheel for {name}=={version} in {lock.name}")
        url, want = best[1]["url"], best[1]["hash"].split(":", 1)[1]
        dest = wheels_dir / url.rsplit("/", 1)[-1]
        if not (dest.is_file() and _sha256(dest) == want):
            _fetch(url, dest, want)
    print(f"  downloaded {len(_pins(binary))} wheels straight from {lock.name} URLs")


def fetch_sdists(lock: Path, sdist_pins: Path, out_dir: Path) -> None:
    pkgs = {_norm(p["name"]): p for p in _lock_packages(lock)}
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, version in sorted(_pins(sdist_pins).items()):
        sd = (pkgs.get(name) or {}).get("sdist")
        if not sd:
            sys.exit(f"no sdist for {name}=={version} in {lock.name}")
        _fetch(sd["url"], out_dir / sd["url"].rsplit("/", 1)[-1], sd["hash"].split(":", 1)[1])
    print(f"  downloaded {len(_pins(sdist_pins))} sdists straight from {lock.name} URLs")


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
    elif cmd == "download" and len(args) == 3:
        download(Path(args[0]), Path(args[1]), Path(args[2]))
    elif cmd == "fetch-sdists" and len(args) == 3:
        fetch_sdists(Path(args[0]), Path(args[1]), Path(args[2]))
    elif cmd == "prune" and len(args) == 2:
        prune(Path(args[0]), Path(args[1]))
    elif cmd == "split" and len(args) == 2:
        split(Path(args[0]), int(args[1]))
    elif cmd == "check" and len(args) in (3, 4):
        check(Path(args[0]), Path(args[1]), int(args[2]), allow_parts="--no-parts" not in args[3:])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
