"""Tests for canonical risk breach persistence mapping."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.sql import ClauseElement

from pmrp.schemas.risk import RiskBreach, RiskLimitScope
from pmrp.storage import PersistenceTimeoutError
from pmrp.storage.models import RiskBreachRow
from pmrp.storage.repositories import (
    RiskBreachRepository,
    risk_breach_from_row,
    risk_breach_to_row,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


def test_risk_breach_to_row_preserves_canonical_payload() -> None:
    breach = _breach()

    row = risk_breach_to_row(breach)

    assert row.breach_id == "breach_01k00000000000000000000000"
    assert row.rule_id == "RISK-POST-001"
    assert row.rule_version == "1.0"
    assert row.scope == "strategy"
    assert row.scope_id == "strat_risk_breach"
    assert row.severity == "critical"
    assert row.detected_at == NOW
    assert row.observed_value == Decimal("125.50")
    assert row.limit_value == Decimal("100.00")
    assert row.unit == "usd"
    assert row.action_taken == "halt_strategy"
    assert row.correlation_id == "corr_risk_breach"
    assert row.resolved_at is None
    assert row.resolution_note is None


def test_risk_breach_from_row_round_trips_canonical_breach() -> None:
    breach = _breach()
    row = risk_breach_to_row(breach)
    row.resolved_at = NOW + timedelta(minutes=10)
    row.resolution_note = "operator reviewed exposure"

    assert risk_breach_from_row(row) == breach


@pytest.mark.asyncio
async def test_repository_add_inserts_row_and_flushes_without_commit() -> None:
    session = _FakeSession()
    repository = RiskBreachRepository(session)  # type: ignore[arg-type]

    await repository.add(_breach())

    assert len(session.added) == 1
    assert isinstance(session.added[0], RiskBreachRow)
    assert session.added[0].breach_id == "breach_01k00000000000000000000000"
    assert session.flushed == 1
    assert session.committed == 0


@pytest.mark.asyncio
async def test_repository_get_queries_breach_id() -> None:
    row = risk_breach_to_row(_breach())
    session = _FakeSession(results=(row,))
    repository = RiskBreachRepository(session)  # type: ignore[arg-type]

    result = await repository.get("breach_01k00000000000000000000000")

    assert result == _breach()
    sql = _compile(session.statements[0])
    assert "risk_breaches.breach_id = 'breach_01k00000000000000000000000'" in sql


@pytest.mark.asyncio
async def test_repository_get_returns_none_when_missing() -> None:
    session = _FakeSession(results=(None,))
    repository = RiskBreachRepository(session)  # type: ignore[arg-type]

    result = await repository.get("breach_01k00000000000000000000000")

    assert result is None


@pytest.mark.asyncio
async def test_repository_list_open_uses_open_severity_query_path() -> None:
    row = risk_breach_to_row(_breach())
    session = _FakeSession(results=((row,),))
    repository = RiskBreachRepository(session)  # type: ignore[arg-type]

    result = await repository.list_open(severity="critical", limit=25)

    assert result == (_breach(),)
    sql = _compile(session.statements[0])
    assert "risk_breaches.resolved_at IS NULL" in sql
    assert "risk_breaches.severity = 'critical'" in sql
    assert "ORDER BY pmrp_risk.risk_breaches.detected_at DESC" in sql
    assert "LIMIT 25" in sql


@pytest.mark.asyncio
async def test_repository_list_open_rejects_invalid_inputs_before_querying() -> None:
    session = _FakeSession()
    repository = RiskBreachRepository(session)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="limit must be positive"):
        await repository.list_open(limit=0)
    with pytest.raises(ValueError, match="severity must not be empty"):
        await repository.list_open(severity="")

    assert session.statements == []


@pytest.mark.asyncio
async def test_repository_resolve_updates_only_open_breach() -> None:
    session = _FakeSession(results=(_FakeUpdateResult(rowcount=1),))
    repository = RiskBreachRepository(session)  # type: ignore[arg-type]

    row_count = await repository.resolve(
        "breach_01k00000000000000000000000",
        resolved_at=NOW + timedelta(minutes=5),
        resolution_note="operator reviewed exposure",
    )

    assert row_count == 1
    assert session.flushed == 1
    assert session.committed == 0
    sql = _compile(session.statements[0])
    assert "UPDATE pmrp_risk.risk_breaches" in sql
    assert "resolved_at='2026-09-22 12:05:00+00:00'" in sql
    assert "resolution_note='operator reviewed exposure'" in sql
    assert "risk_breaches.breach_id = 'breach_01k00000000000000000000000'" in sql
    assert "risk_breaches.resolved_at IS NULL" in sql


@pytest.mark.asyncio
async def test_repository_resolve_rejects_empty_resolution_note() -> None:
    session = _FakeSession()
    repository = RiskBreachRepository(session)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="resolution note must not be empty"):
        await repository.resolve(
            "breach_01k00000000000000000000000",
            resolved_at=NOW,
            resolution_note="",
        )

    assert session.statements == []


@pytest.mark.asyncio
async def test_repository_classifies_sqlalchemy_execute_errors() -> None:
    session = _FakeSession(execute_error=SQLAlchemyTimeoutError("pool exhausted"))
    repository = RiskBreachRepository(session)  # type: ignore[arg-type]

    with pytest.raises(PersistenceTimeoutError, match="timed out"):
        await repository.list_open()


@pytest.mark.asyncio
async def test_repository_classifies_flush_errors() -> None:
    session = _FakeSession(flush_error=SQLAlchemyTimeoutError("pool exhausted"))
    repository = RiskBreachRepository(session)  # type: ignore[arg-type]

    with pytest.raises(PersistenceTimeoutError, match="timed out"):
        await repository.add(_breach())


def _breach(**overrides: object) -> RiskBreach:
    payload: dict[str, object] = {
        "breach_id": "breach_01k00000000000000000000000",
        "rule_id": "RISK-POST-001",
        "rule_version": "1.0",
        "scope": RiskLimitScope.STRATEGY,
        "scope_id": "strat_risk_breach",
        "severity": "critical",
        "detected_at": NOW,
        "observed_value": "125.50",
        "limit_value": "100.00",
        "unit": "usd",
        "action_taken": "halt_strategy",
        "correlation_id": "corr_risk_breach",
    }
    payload.update(overrides)
    return RiskBreach.model_validate(payload)


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
        self.added: list[RiskBreachRow] = []
        self.statements: list[ClauseElement] = []
        self.flushed = 0
        self.committed = 0
        self._results = list(results)
        self._execute_error = execute_error
        self._flush_error = flush_error

    def add(self, row: RiskBreachRow) -> None:
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

    def scalar_one_or_none(self) -> RiskBreachRow | None:
        if self._value is None:
            return None
        return self._value  # type: ignore[return-value]

    def scalars(self) -> _FakeResult:
        return self

    def all(self) -> list[RiskBreachRow]:
        if self._value is None:
            return []
        if isinstance(self._value, tuple):
            return list(self._value)  # type: ignore[return-value]
        return [self._value]  # type: ignore[list-item]


class _FakeUpdateResult:
    def __init__(self, *, rowcount: int) -> None:
        self.rowcount = rowcount
