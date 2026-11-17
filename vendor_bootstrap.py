#!/usr/bin/env python3
"""Start OntoBricks from vendored wheels, with no package index.

The deployment workspace has no PyPI egress (Apps builds, serverless and
classic compute all fail to reach pypi.org), so every runtime dependency
ships with the app under ``vendor/``. ``scripts/build_artifact.sh`` builds it
on a machine that can reach PyPI, following hello-abacus's
``scripts/build_artifact.sh``.

hello-abacus lets the Apps container install ``requirements.txt`` from
``./wheels`` at build time. OntoBricks cannot do that for its main app:
several wheels (pyarrow, scipy, numpy, pandas, mlflow) are over the 10 MB
Apps file limit, so they are stored as ``<wheel>.partNN`` chunks, which pip
cannot read. This script therefore runs as the app command and:

1. reassembles the chunks into whole wheels,
2. installs ``vendor/requirements.txt`` with ``--no-index --no-deps`` into a
   writable target directory, skipped when that lock is already installed,
3. execs ``run.py`` with the target first on ``PYTHONPATH``, so the locked
   versions win over the Apps image's pre-installed ones.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / "vendor"
PART_MARKER = ".whl.part"


def _log(msg: str) -> None:
    print(f"vendor_bootstrap: {msg}", flush=True)


def reassemble(wheels_dir: Path, dest: Path) -> int:
    """Put every vendored wheel, whole, in ``dest``. Returns the wheel count.

    Whole wheels are linked (copied if links are unsupported); chunked ones
    (``<name>.whl.part00``, ``.part01``, ...) are concatenated in order.
    """
    dest.mkdir(parents=True, exist_ok=True)
    chunks: dict[str, list[Path]] = {}
    count = 0
    for f in sorted(wheels_dir.iterdir()):
        if f.name.endswith(".whl"):
            try:
                os.symlink(f.resolve(), dest / f.name)
            except OSError:
                shutil.copyfile(f, dest / f.name)
            count += 1
        elif PART_MARKER in f.name:
            wheel_name = f.name.split(PART_MARKER, 1)[0] + ".whl"
            chunks.setdefault(wheel_name, []).append(f)
    for wheel_name, parts in chunks.items():
        parts.sort(key=lambda p: int(p.name.split(PART_MARKER, 1)[1]))
        with open(dest / wheel_name, "wb") as out:
            for part in parts:
                with open(part, "rb") as src:
                    shutil.copyfileobj(src, out)
        count += 1
    return count


def install(site_dir: Path, wheels_dir: Path, requirements: Path) -> None:
    """Install the pinned set offline. uv (in the Apps image) first, then pip."""
    common = ["--no-index", "--no-deps", "--find-links", str(wheels_dir),
              "--target", str(site_dir), "-r", str(requirements)]
    uv = shutil.which("uv")
    if uv:
        try:
            subprocess.run([uv, "pip", "install", "--offline", "--python", sys.executable, *common],
                           check=True)
            return
        except subprocess.CalledProcessError as exc:
            _log(f"uv install failed (exit {exc.returncode}); retrying with pip")
            shutil.rmtree(site_dir, ignore_errors=True)
    subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                    "--no-cache-dir", *common], check=True)


def ensure_installed(vendor: Path = VENDOR, base: Path | None = None) -> Path:
    """Install the vendored lock once per container; return its site dir."""
    requirements = vendor / "requirements.txt"
    if not requirements.is_file():
        _log(f"FATAL: {requirements} is missing. Build it with `make artifact` "
             "(scripts/build_artifact.sh) on a machine that can reach PyPI, then redeploy.")
        sys.exit(1)
    stamp = vendor / "lock.sha256"
    key = stamp.read_text().strip()[:16] if stamp.is_file() else "unversioned"
    base = base or Path(os.environ.get("ONTOBRICKS_VENDOR_DIR")
                        or Path(tempfile.gettempdir()) / "ontobricks-vendor")
    home = base / key
    site_dir = home / "site"
    marker = home / ".installed"
    if marker.is_file():
        _log(f"lock {key} already installed in {site_dir}")
        return site_dir
    shutil.rmtree(home, ignore_errors=True)
    started = time.monotonic()
    count = reassemble(vendor / "wheels", home / "wheels")
    _log(f"installing {count} vendored wheels offline into {site_dir}")
    install(site_dir, home / "wheels", requirements)
    shutil.rmtree(home / "wheels", ignore_errors=True)
    marker.write_text(key)
    _log(f"installed in {time.monotonic() - started:.0f}s")
    return site_dir


def main() -> None:
    site_dir = ensure_installed()
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(p for p in (str(site_dir), env.get("PYTHONPATH", "")) if p)
    os.execve(sys.executable, [sys.executable, str(ROOT / "run.py"), *sys.argv[1:]], env)


if __name__ == "__main__":
    main()
