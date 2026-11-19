import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from backend.adapters.forwarded_identity import ForwardedIdentity
from backend.adapters.memory_app_state import MemoryAppState
from backend.features.items import route, sql
from backend.kernel.errors import Unauthorized

SIGNED_IN = {
    "x-forwarded-user": "1234@5678",
    "x-forwarded-email": "ada@example.com",
    "x-forwarded-access-token": "user-token",
}


@pytest.fixture
def state() -> MemoryAppState:
    return MemoryAppState()


@pytest.fixture
def client(state: MemoryAppState) -> TestClient:
    app = FastAPI()
    app.include_router(route.router(state=state, identity=ForwardedIdentity()))

    # The same mapping runtime/ registers, so a missing user reads as a 401 here too.
    @app.exception_handler(Unauthorized)
    def unauthorized(_: Request, exc: Unauthorized) -> JSONResponse:
        return JSONResponse(status_code=401, content={"detail": str(exc)})

    return TestClient(app)


def test_lists_items_as_the_signed_in_user(client: TestClient, state: MemoryAppState) -> None:
    state.respond(sql.LIST_ITEMS, lambda _: [{"id": 1, "name": "first"}])

    response = client.get("/api/items", headers=SIGNED_IN)

    assert response.status_code == 200
    assert response.json() == [{"id": 1, "name": "first"}]
    caller, _, _ = state.calls[0]
    assert caller.user_name == "ada@example.com"


def test_creates_an_item_recording_the_actor(client: TestClient, state: MemoryAppState) -> None:
    state.respond(sql.CREATE_ITEM, lambda params: [{"id": 7, "name": params["name"]}])

    response = client.post("/api/items", json={"name": "second"}, headers=SIGNED_IN)

    assert response.status_code == 201
    assert response.json() == {"id": 7, "name": "second"}
    _, statement, params = state.calls[0]
    assert statement == sql.CREATE_ITEM
    assert params == {"name": "second", "created_by": "ada@example.com"}


def test_rejects_an_empty_name(client: TestClient, state: MemoryAppState) -> None:
    response = client.post("/api/items", json={"name": ""}, headers=SIGNED_IN)

    assert response.status_code == 422
    assert state.calls == []


@pytest.mark.parametrize("method", ["get", "post"])
def test_refuses_a_request_without_a_user(client: TestClient, state: MemoryAppState, method: str) -> None:
    response = client.request(method, "/api/items", json={"name": "x"})

    assert response.status_code == 401
    assert state.calls == []


def test_refuses_a_request_without_a_token(client: TestClient, state: MemoryAppState) -> None:
    headers = {k: v for k, v in SIGNED_IN.items() if k != "x-forwarded-access-token"}

    response = client.get("/api/items", headers=headers)

    assert response.status_code == 401
    assert state.calls == []
