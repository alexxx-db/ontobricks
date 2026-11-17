from collections.abc import Mapping
from dataclasses import dataclass

import psycopg
from databricks.sdk import WorkspaceClient
from psycopg.rows import dict_row

from backend.kernel.errors import Unauthorized
from backend.kernel.identity import UserToken
from backend.ports.app_state import Row

# Lakebase listens on the standard Postgres port and requires TLS.
PORT = 5432
SSLMODE = "require"


@dataclass(frozen=True)
class LakebaseConfig:
    workspace_host: str
    endpoint: str
    host: str
    database: str


class LakebaseAppState:
    """AppStatePort on Lakebase, connected as the signed-in user's own Postgres role.

    Each call mints a database credential with the user's token and opens a connection
    as that user, so grants and row-level security apply to the person. Connections are
    never shared across users.
    """

    def __init__(self, config: LakebaseConfig) -> None:
        self._config = config

    def fetch_all(self, caller: UserToken, statement: str, params: Mapping[str, object]) -> list[Row]:
        with self._connect(caller) as conn:
            return conn.execute(statement, params).fetchall()

    def fetch_one(self, caller: UserToken, statement: str, params: Mapping[str, object]) -> Row:
        with self._connect(caller) as conn:
            row = conn.execute(statement, params).fetchone()
        if row is None:
            raise LookupError("The statement returned no row")
        return row

    def _connect(self, caller: UserToken) -> psycopg.Connection[Row]:
        if not isinstance(caller, UserToken):
            raise Unauthorized("Lakebase requires the signed-in user's token")
        # auth_type pins the user's token, so the app's own service principal
        # credentials in the environment are never used instead.
        workspace = WorkspaceClient(host=self._config.workspace_host, token=caller.value, auth_type="pat")
        credential = workspace.postgres.generate_database_credential(endpoint=self._config.endpoint)
        return psycopg.connect(
            host=self._config.host,
            port=PORT,
            dbname=self._config.database,
            user=caller.user_name,
            password=credential.token,
            sslmode=SSLMODE,
            row_factory=dict_row,
        )
