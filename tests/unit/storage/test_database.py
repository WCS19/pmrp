"""Tests for storage engine creation and health checks."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import OperationalError

from pmrp.storage import DatabaseConfig, PersistenceUnavailableError
from pmrp.storage import database as database_module


@pytest.mark.unit
def test_create_database_engine_uses_configured_pool_and_timeouts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    sentinel = object()

    def fake_create_async_engine(url: str, **kwargs: object) -> object:
        captured["url"] = url
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(database_module, "create_async_engine", fake_create_async_engine)

    config = DatabaseConfig(
        url="postgresql+asyncpg://user:password@localhost/pmrp",
        application_name="pmrp-storage-test",
        pool_min_size=2,
        pool_max_size=7,
        pool_timeout_seconds=4,
        pool_recycle_seconds=120,
        connect_timeout_seconds=3,
        require_tls=False,
    )

    engine = database_module.create_database_engine(config)

    assert engine is sentinel
    assert captured["url"] == "postgresql+asyncpg://user:password@localhost/pmrp"
    assert captured["pool_size"] == 2
    assert captured["max_overflow"] == 5
    assert captured["pool_timeout"] == 4
    assert captured["pool_recycle"] == 120
    assert captured["pool_pre_ping"] is True
    assert captured["connect_args"] == config.connect_args


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_database_health_reports_version_timezone_and_utc() -> None:
    engine = _FakeEngine(version="16.4", timezone="UTC")

    health = await database_module.check_database_health(engine)

    assert health.reachable is True
    assert health.server_version == "16.4"
    assert health.session_timezone == "UTC"
    assert health.is_utc is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_database_health_rejects_non_utc_timezone() -> None:
    engine = _FakeEngine(version="16.4", timezone="America/Denver")

    with pytest.raises(PersistenceUnavailableError) as exc_info:
        await database_module.check_database_health(engine)

    assert exc_info.value.retryable is False
    assert exc_info.value.context == {"session_timezone": "America/Denver"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_database_health_classifies_connection_failures() -> None:
    engine = _FailingEngine(
        OperationalError(
            "SHOW server_version",
            {},
            _SqlState("08006"),
        )
    )

    with pytest.raises(PersistenceUnavailableError) as exc_info:
        await database_module.check_database_health(engine)

    assert exc_info.value.retryable is True
    assert exc_info.value.context == {"sqlstate": "08006"}


class _SqlState:
    def __init__(self, sqlstate: str) -> None:
        self.sqlstate = sqlstate


class _Result:
    def __init__(self, value: str) -> None:
        self._value = value

    def scalar_one(self) -> str:
        return self._value


class _Connection:
    def __init__(self, *, version: str, timezone: str) -> None:
        self._version = version
        self._timezone = timezone

    async def execute(self, statement: object) -> _Result:
        statement_text = str(statement)
        if "server_version" in statement_text:
            return _Result(self._version)
        return _Result(self._timezone)


class _ConnectionContext:
    def __init__(self, connection: _Connection) -> None:
        self._connection = connection

    async def __aenter__(self) -> _Connection:
        return self._connection

    async def __aexit__(self, *_args: object) -> None:
        return None


class _FakeEngine:
    def __init__(self, *, version: str, timezone: str) -> None:
        self._connection = _Connection(version=version, timezone=timezone)

    def connect(self) -> _ConnectionContext:
        return _ConnectionContext(self._connection)


class _FailingConnectionContext:
    def __init__(self, error: OperationalError) -> None:
        self._error = error

    async def __aenter__(self) -> _Connection:
        raise self._error

    async def __aexit__(self, *_args: object) -> None:
        return None


class _FailingEngine:
    def __init__(self, error: OperationalError) -> None:
        self._error = error

    def connect(self) -> _FailingConnectionContext:
        return _FailingConnectionContext(self._error)
