"""Idle-connection liveness checks for the Lakebase connection pool."""

from __future__ import annotations

import types
from unittest.mock import Mock

import pytest

import importlib

from back.core.databricks.lakebase.LakebaseConnectionPool import (
    LakebaseConnectionPool,
)

# The package __init__ re-exports the class under the module's name, so
# resolve the module itself to patch its clock.
pool_module = importlib.import_module(
    "back.core.databricks.lakebase.LakebaseConnectionPool"
)
from back.core.databricks.lakebase.constants import POOL_PING_IDLE_S


class _Conn:
    """Minimal psycopg connection stand-in tracking execute + close."""

    def __init__(self, *, ping_error=None):
        self.closed = False
        self.executed: list = []
        self._ping_error = ping_error

    def cursor(self):
        conn = self

        class _Cur:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def execute(self, sql):
                conn.executed.append(sql)
                if conn._ping_error is not None:
                    raise conn._ping_error

        return _Cur()

    def close(self):
        self.closed = True


def _pool(**kwargs) -> LakebaseConnectionPool:
    return LakebaseConnectionPool(
        auth=Mock(), schema="s", application_name="t", **kwargs
    )


@pytest.fixture
def clock(monkeypatch):
    """Replace the pool module's clock with a controllable monotonic."""
    tick = [1000.0]
    monkeypatch.setattr(
        pool_module,
        "time",
        types.SimpleNamespace(
            monotonic=lambda: tick[0],
            sleep=lambda s: None,
        ),
    )
    return tick


def test_recently_used_conn_is_lent_without_ping(clock):
    pool = _pool()
    conn = _Conn()
    pool._open_one = lambda: conn

    with pool.connection() as lent:
        assert lent is conn
    clock[0] += POOL_PING_IDLE_S - 1
    with pool.connection() as lent:
        assert lent is conn

    assert "SELECT 1" not in conn.executed


def test_parked_conn_is_pinged_before_checkout(clock):
    pool = _pool()
    conn = _Conn()
    pool._open_one = lambda: conn

    with pool.connection():
        pass
    clock[0] += POOL_PING_IDLE_S + 1
    with pool.connection() as lent:
        assert lent is conn

    assert conn.executed == ["SELECT 1"]


def test_failed_ping_discards_conn_and_opens_fresh(clock):
    pool = _pool()
    stale = _Conn(ping_error=RuntimeError("socket gone"))
    fresh = _Conn()
    conns = iter([stale, fresh])
    pool._open_one = lambda: next(conns)

    with pool.connection():
        pass
    clock[0] += POOL_PING_IDLE_S + 1
    with pool.connection() as lent:
        assert lent is fresh

    assert stale.closed is True
    assert pool.stats()["size"] == 1


def test_closed_conn_is_discarded_without_ping(clock):
    pool = _pool()
    dead = _Conn()
    fresh = _Conn()
    conns = iter([dead, fresh])
    pool._open_one = lambda: next(conns)

    with pool.connection():
        pass
    dead.closed = True  # locally-observed close — no round-trip needed
    clock[0] += POOL_PING_IDLE_S + 1
    with pool.connection() as lent:
        assert lent is fresh

    assert dead.executed == []
