from collections.abc import Mapping
from typing import Protocol

from backend.kernel.identity import UserToken

Row = dict[str, object]


class AppStatePort(Protocol):
    """App-owned state in Lakebase, accessed as the signed-in user's Postgres role.

    Statements use `%(name)s` parameters. Every method raises Unauthorized when
    `caller` is not a UserToken.
    """

    def fetch_all(self, caller: UserToken, statement: str, params: Mapping[str, object]) -> list[Row]: ...

    def fetch_one(self, caller: UserToken, statement: str, params: Mapping[str, object]) -> Row:
        """The statement's first row. Raises LookupError when it returns none."""
        ...
