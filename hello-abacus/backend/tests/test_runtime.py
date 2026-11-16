from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.runtime import config
from backend.runtime.app import create_app

ENVIRON = {
    "DATABRICKS_APP_PORT": "8000",
    "DATABRICKS_HOST": "https://example.cloud.databricks.com",
    "ENDPOINT_NAME": "projects/p/branches/production/endpoints/primary",
    "PGHOST": "instance.database.cloud.databricks.com",
    "PGDATABASE": "app",
}


@pytest.mark.parametrize("missing", list(ENVIRON))
def test_startup_fails_naming_a_missing_variable(missing: str) -> None:
    environ = {k: v for k, v in ENVIRON.items() if k != missing}
    with pytest.raises(config.MissingConfig, match=missing):
        config.load(environ)


def test_the_wired_app_serves_health_and_refuses_anonymous_requests(tmp_path: Path) -> None:
    settings = replace(config.load(ENVIRON), static_dir=tmp_path)
    client = TestClient(create_app(settings))

    assert client.get("/health").status_code == 200
    assert client.get("/api/items").status_code == 401
    assert client.get("/api/me").status_code == 401
