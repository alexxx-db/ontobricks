import pytest

from backend.adapters.forwarded_identity import ForwardedIdentity
from backend.kernel.errors import Unauthorized
from backend.kernel.identity import Actor
from backend.ports.identity import IdentityPort

SIGNED_IN = {
    "x-forwarded-user": "1234@5678",
    "x-forwarded-email": "ada@example.com",
    "x-forwarded-access-token": "user-token",
}


@pytest.fixture(params=[ForwardedIdentity])
def adapter(request: pytest.FixtureRequest) -> IdentityPort:
    return request.param()


def test_reads_the_signed_in_user(adapter: IdentityPort) -> None:
    assert adapter.actor(SIGNED_IN) == Actor(user="1234@5678", email="ada@example.com")
    token = adapter.user_token(SIGNED_IN)
    assert (token.user_name, token.value) == ("ada@example.com", "user-token")


@pytest.mark.parametrize("missing", ["x-forwarded-user", "x-forwarded-email"])
def test_actor_fails_closed_without_the_user(adapter: IdentityPort, missing: str) -> None:
    with pytest.raises(Unauthorized):
        adapter.actor({k: v for k, v in SIGNED_IN.items() if k != missing})


@pytest.mark.parametrize("missing", ["x-forwarded-access-token", "x-forwarded-email"])
def test_user_token_fails_closed_without_the_token(adapter: IdentityPort, missing: str) -> None:
    with pytest.raises(Unauthorized):
        adapter.user_token({k: v for k, v in SIGNED_IN.items() if k != missing})


def test_the_token_never_appears_in_repr(adapter: IdentityPort) -> None:
    assert "user-token" not in repr(adapter.user_token(SIGNED_IN))
