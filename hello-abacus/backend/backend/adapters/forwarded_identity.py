from collections.abc import Mapping

from backend.kernel.errors import Unauthorized
from backend.kernel.identity import Actor, UserToken


class ForwardedIdentity:
    """IdentityPort on the headers Databricks Apps forwards with every request.

    It has no backend to replace, so it is also the adapter tests use.
    """

    def actor(self, headers: Mapping[str, str]) -> Actor:
        user = headers.get("x-forwarded-user")
        email = headers.get("x-forwarded-email")
        if not user or not email:
            raise Unauthorized("No forwarded user")
        return Actor(user=user, email=email)

    def user_token(self, headers: Mapping[str, str]) -> UserToken:
        token = headers.get("x-forwarded-access-token")
        email = headers.get("x-forwarded-email")
        if not token or not email:
            raise Unauthorized("No forwarded access token")
        return UserToken(user_name=email, value=token)
