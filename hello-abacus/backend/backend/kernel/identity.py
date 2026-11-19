from dataclasses import dataclass, field


@dataclass(frozen=True)
class Actor:
    """The signed-in person, recorded on app-owned writes."""

    user: str
    email: str


@dataclass(frozen=True)
class UserToken:
    """The signed-in user's forwarded token, required by every port that reads or writes data.

    `user_name` is the Databricks user the token was issued to. A Lakebase adapter
    connects as the Postgres role of that name.
    """

    user_name: str
    value: str = field(repr=False)
