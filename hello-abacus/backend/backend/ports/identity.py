from collections.abc import Mapping
from typing import Protocol

from backend.kernel.identity import Actor, UserToken


class IdentityPort(Protocol):
    def actor(self, headers: Mapping[str, str]) -> Actor:
        """The signed-in person. Raises Unauthorized when the headers are missing."""
        ...

    def user_token(self, headers: Mapping[str, str]) -> UserToken:
        """The forwarded token for data ports. Raises Unauthorized when missing."""
        ...
