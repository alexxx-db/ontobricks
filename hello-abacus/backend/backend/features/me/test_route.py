import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from backend.adapters.forwarded_identity import ForwardedIdentity
from backend.features.me import route
from backend.kernel.errors import Unauthorized

SIGNED_IN = {
    "x-forwarded-user": "1234@5678",
    "x-forwarded-email": "ada@example.com",
}


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(route.router(identity=ForwardedIdentity()))

    # The same mapping runtime/ registers, so a missing user reads as a 401 here too.
    @app.exception_handler(Unauthorized)
    def unauthorized(_: Request, exc: Unauthorized) -> JSONResponse:
        return JSONResponse(status_code=401, content={"detail": str(exc)})

    return TestClient(app)


def test_returns_the_signed_in_user(client: TestClient) -> None:
    response = client.get("/api/me", headers=SIGNED_IN)

    assert response.status_code == 200
    assert response.json() == {"email": "ada@example.com"}


def test_refuses_a_request_with_no_forwarded_user(client: TestClient) -> None:
    assert client.get("/api/me").status_code == 401
