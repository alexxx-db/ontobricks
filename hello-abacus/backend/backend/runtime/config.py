import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from backend.adapters.lakebase import LakebaseConfig

# The frontend build writes here; see frontend/vite.config.ts.
STATIC_DIR = Path(__file__).resolve().parents[2] / "dist"


class MissingConfig(RuntimeError):
    """A required environment variable is absent. Startup fails naming it."""


@dataclass(frozen=True)
class Config:
    port: int
    static_dir: Path
    lakebase: LakebaseConfig


def load(environ: Mapping[str, str] = os.environ) -> Config:
    """Read every variable the app needs, once, at startup. There are no defaults."""

    def require(name: str) -> str:
        value = environ.get(name)
        if not value:
            raise MissingConfig(f"Required environment variable {name} is not set")
        return value

    return Config(
        port=int(require("DATABRICKS_APP_PORT")),
        static_dir=STATIC_DIR,
        lakebase=LakebaseConfig(
            workspace_host=require("DATABRICKS_HOST"),
            endpoint=require("ENDPOINT_NAME"),
            host=require("PGHOST"),
            database=require("PGDATABASE"),
        ),
    )
