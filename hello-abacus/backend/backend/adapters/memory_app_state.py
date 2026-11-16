from collections.abc import Callable, Mapping

from backend.kernel.errors import Unauthorized
from backend.kernel.identity import UserToken
from backend.ports.app_state import Row

Responder = Callable[[Mapping[str, object]], list[Row]]


class MemoryAppState:
    """AppStatePort in memory, for tests. It runs no SQL.

    A statement returns the rows `respond` scripted for it, or none. Every call is
    recorded in `calls`, so a test can check what a slice sent and as whom.
    """

    def __init__(self) -> None:
        self._responders: dict[str, Responder] = {}
        self.calls: list[tuple[UserToken, str, Mapping[str, object]]] = []

    def respond(self, statement: str, responder: Responder) -> None:
        self._responders[statement] = responder

    def fetch_all(self, caller: UserToken, statement: str, params: Mapping[str, object]) -> list[Row]:
        if not isinstance(caller, UserToken):
            raise Unauthorized("App state requires the signed-in user's token")
        self.calls.append((caller, statement, params))
        responder = self._responders.get(statement)
        return responder(params) if responder else []

    def fetch_one(self, caller: UserToken, statement: str, params: Mapping[str, object]) -> Row:
        rows = self.fetch_all(caller, statement, params)
        if not rows:
            raise LookupError("The statement returned no row")
        return rows[0]
