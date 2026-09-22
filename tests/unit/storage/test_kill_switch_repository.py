"""Tests for durable risk kill switch persistence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.sql import ClauseElement

from pmrp.schemas.risk import KillSwitchScope, KillSwitchState
from pmrp.storage import PersistenceTimeoutError
from pmrp.storage.models import KillSwitchRow
from pmrp.storage.repositories import (
    KillSwitchRepository,
    kill_switch_from_row,
    kill_switch_to_row,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


def test_kill_switch_to_row_preserves_active_canonical_payload() -> None:
    kill_switch = _active_switch()

    row = kill_switch_to_row(kill_switch)

    assert row.kill_switch_id == "kill_01k00000000000000000000000"
    assert row.scope == "strategy"
    assert row.scope_id == "strat_kill_switch"
    assert row.active is True
    assert row.activated_at == NOW
    assert row.activated_by == "risk_operator"
    assert row.activation_reason == "operator drill"
    assert row.released_at is None
    assert row.released_by is None
    assert row.release_reason is None
    assert row.aggregate_version == 0


def test_kill_switch_from_row_round_trips_active_state() -> None:
    kill_switch = _active_switch()
    row = kill_switch_to_row(kill_switch)
    row.created_at = NOW
    row.updated_at = NOW + timedelta(minutes=1)

    assert kill_switch_from_row(row) == kill_switch


def test_kill_switch_from_row_round_trips_released_state() -> None:
    kill_switch = _released_switch()
    row = kill_switch_to_row(kill_switch)

    assert kill_switch_from_row(row) == kill_switch


@pytest.mark.asyncio
async def test_repository_add_inserts_row_and_flushes_without_commit() -> None:
    session = _FakeSession()
    repository = KillSwitchRepository(session)  # type: ignore[arg-type]

    await repository.add(_active_switch())

    assert len(session.added) == 1
    assert isinstance(session.added[0], KillSwitchRow)
    assert session.added[0].kill_switch_id == "kill_01k00000000000000000000000"
    assert session.flushed == 1
    assert session.committed == 0


@pytest.mark.asyncio
async def test_repository_get_queries_kill_switch_id() -> None:
    row = kill_switch_to_row(_active_switch())
    session = _FakeSession(results=(row,))
    repository = KillSwitchRepository(session)  # type: ignore[arg-type]

    result = await repository.get("kill_01k00000000000000000000000")

    assert result == _active_switch()
    sql = _compile(session.statements[0])
    assert "kill_switches.kill_switch_id = 'kill_01k00000000000000000000000'" in sql


@pytest.mark.asyncio
async def test_repository_get_returns_none_when_missing() -> None:
    session = _FakeSession(results=(None,))
    repository = KillSwitchRepository(session)  # type: ignore[arg-type]

    result = await repository.get("kill_01k00000000000000000000000")

    assert result is None


@pytest.mark.asyncio
async def test_repository_list_active_uses_documented_scope_filters() -> None:
    row = kill_switch_to_row(_active_switch())
    session = _FakeSession(results=((row,),))
    repository = KillSwitchRepository(session)  # type: ignore[arg-type]

    result = await repository.list_active(
        scope=KillSwitchScope.STRATEGY,
        scope_id="strat_kill_switch",
        limit=25,
    )

    assert result == (_active_switch(),)
    sql = _compile(session.statements[0])
    assert "kill_switches.active IS true" in sql
    assert "kill_switches.scope = 'strategy'" in sql
    assert "kill_switches.scope_id = 'strat_kill_switch'" in sql
    assert "ORDER BY pmrp_risk.kill_switches.scope, pmrp_risk.kill_switches.scope_id" in sql
    assert "pmrp_risk.kill_switches.kill_switch_id" in sql
    assert "LIMIT 25" in sql


@pytest.mark.asyncio
async def test_repository_list_active_accepts_schema_valid_scope_id_length() -> None:
    scope_id = "scope_" + ("a" * 250)
    row = kill_switch_to_row(_active_switch(scope_id=scope_id))
    session = _FakeSession(results=((row,),))
    repository = KillSwitchRepository(session)  # type: ignore[arg-type]

    result = await repository.list_active(scope_id=scope_id)

    assert result == (_active_switch(scope_id=scope_id),)
    sql = _compile(session.statements[0])
    assert f"kill_switches.scope_id = '{scope_id}'" in sql


@pytest.mark.asyncio
async def test_repository_list_active_rejects_invalid_inputs_before_querying() -> None:
    session = _FakeSession()
    repository = KillSwitchRepository(session)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="limit must be positive"):
        await repository.list_active(limit=0)
    with pytest.raises(ValueError, match="scope_id must not be empty"):
        await repository.list_active(scope_id="")

    assert session.statements == []


@pytest.mark.asyncio
async def test_repository_release_updates_only_active_unreleased_switch() -> None:
    session = _FakeSession(results=(_FakeUpdateResult(rowcount=1),))
    repository = KillSwitchRepository(session)  # type: ignore[arg-type]

    row_count = await repository.release(
        "kill_01k00000000000000000000000",
        released_at=NOW + timedelta(minutes=5),
        released_by="risk_operator",
        release_reason="drill complete",
    )

    assert row_count == 1
    assert session.flushed == 1
    assert session.committed == 0
    sql = _compile(session.statements[0])
    assert "UPDATE pmrp_risk.kill_switches" in sql
    assert "active=false" in sql
    assert "released_at='2026-09-22 12:05:00+00:00'" in sql
    assert "released_by='risk_operator'" in sql
    assert "release_reason='drill complete'" in sql
    assert "updated_at='2026-09-22 12:05:00+00:00'" in sql
    assert "aggregate_version=(pmrp_risk.kill_switches.aggregate_version + 1)" in sql
    assert "kill_switches.kill_switch_id = 'kill_01k00000000000000000000000'" in sql
    assert "kill_switches.active IS true" in sql
    assert "kill_switches.released_at IS NULL" in sql


@pytest.mark.asyncio
async def test_repository_release_rejects_empty_audit_fields_before_querying() -> None:
    session = _FakeSession()
    repository = KillSwitchRepository(session)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="released_by must not be empty"):
        await repository.release(
            "kill_01k00000000000000000000000",
            released_at=NOW,
            released_by="",
            release_reason="drill complete",
        )
    with pytest.raises(ValueError, match="release_reason must not be empty"):
        await repository.release(
            "kill_01k00000000000000000000000",
            released_at=NOW,
            released_by="risk_operator",
            release_reason="",
        )

    assert session.statements == []


@pytest.mark.asyncio
async def test_repository_classifies_sqlalchemy_execute_errors() -> None:
    session = _FakeSession(execute_error=SQLAlchemyTimeoutError("pool exhausted"))
    repository = KillSwitchRepository(session)  # type: ignore[arg-type]

    with pytest.raises(PersistenceTimeoutError, match="timed out"):
        await repository.list_active()


@pytest.mark.asyncio
async def test_repository_classifies_flush_errors() -> None:
    session = _FakeSession(flush_error=SQLAlchemyTimeoutError("pool exhausted"))
    repository = KillSwitchRepository(session)  # type: ignore[arg-type]

    with pytest.raises(PersistenceTimeoutError, match="timed out"):
        await repository.add(_active_switch())


def _active_switch(**overrides: object) -> KillSwitchState:
    payload: dict[str, object] = {
        "kill_switch_id": "kill_01k00000000000000000000000",
        "scope": KillSwitchScope.STRATEGY,
        "scope_id": "strat_kill_switch",
        "active": True,
        "activated_at": NOW,
        "activated_by": "risk_operator",
        "activation_reason": "operator drill",
        "released_at": None,
        "released_by": None,
        "release_reason": None,
        "version": 0,
    }
    payload.update(overrides)
    return KillSwitchState.model_validate(payload)


def _released_switch(**overrides: object) -> KillSwitchState:
    payload: dict[str, object] = {
        "kill_switch_id": "kill_01k00000000000000000000000",
        "scope": KillSwitchScope.STRATEGY,
        "scope_id": "strat_kill_switch",
        "active": False,
        "activated_at": NOW,
        "activated_by": "risk_operator",
        "activation_reason": "operator drill",
        "released_at": NOW + timedelta(minutes=5),
        "released_by": "risk_operator",
        "release_reason": "drill complete",
        "version": 1,
    }
    payload.update(overrides)
    return KillSwitchState.model_validate(payload)


def _compile(statement: ClauseElement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


class _FakeSession:
    def __init__(
        self,
        *,
        results: tuple[object, ...] = (),
        execute_error: Exception | None = None,
        flush_error: Exception | None = None,
    ) -> None:
        self.added: list[KillSwitchRow] = []
        self.statements: list[ClauseElement] = []
        self.flushed = 0
        self.committed = 0
        self._results = list(results)
        self._execute_error = execute_error
        self._flush_error = flush_error

    def add(self, row: KillSwitchRow) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        if self._flush_error is not None:
            raise self._flush_error
        self.flushed += 1

    async def execute(self, statement: ClauseElement) -> _FakeResult | _FakeUpdateResult:
        if self._execute_error is not None:
            raise self._execute_error
        self.statements.append(statement)
        value = self._results.pop(0) if self._results else None
        if isinstance(value, _FakeUpdateResult):
            return value
        return _FakeResult(value)


class _FakeResult:
    def __init__(self, value: object) -> None:
        self._value = value

    def scalar_one_or_none(self) -> KillSwitchRow | None:
        if self._value is None:
            return None
        return self._value  # type: ignore[return-value]

    def scalars(self) -> _FakeResult:
        return self

    def all(self) -> list[KillSwitchRow]:
        if self._value is None:
            return []
        if isinstance(self._value, tuple):
            return list(self._value)  # type: ignore[return-value]
        return [self._value]  # type: ignore[list-item]


class _FakeUpdateResult:
    def __init__(self, *, rowcount: int) -> None:
        self.rowcount = rowcount
