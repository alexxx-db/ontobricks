from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.features.health import route


def test_health_needs_no_user() -> None:
    app = FastAPI()
    app.include_router(route.router())

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
