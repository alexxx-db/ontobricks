import pytest

from backend.adapters.memory_app_state import MemoryAppState
from backend.kernel.errors import Unauthorized
from backend.kernel.identity import UserToken
from backend.ports.app_state import AppStatePort

# The real adapter, LakebaseAppState, needs a reachable Lakebase. It is held to this
# contract in the deployed dev smoke, not here.
CALLER = UserToken(user_name="ada@example.com", value="user-token")
NO_ROWS = "SELECT 1 WHERE false"


@pytest.fixture(params=[MemoryAppState])
def adapter(request: pytest.FixtureRequest) -> AppStatePort:
    return request.param()


@pytest.mark.parametrize("method", ["fetch_all", "fetch_one"])
def test_refuses_a_call_without_a_user(adapter: AppStatePort, method: str) -> None:
    with pytest.raises(Unauthorized):
        getattr(adapter, method)(None, NO_ROWS, {})


def test_fetch_all_returns_no_rows_as_an_empty_list(adapter: AppStatePort) -> None:
    assert adapter.fetch_all(CALLER, NO_ROWS, {}) == []


def test_fetch_one_raises_when_there_is_no_row(adapter: AppStatePort) -> None:
    with pytest.raises(LookupError):
        adapter.fetch_one(CALLER, NO_ROWS, {})
