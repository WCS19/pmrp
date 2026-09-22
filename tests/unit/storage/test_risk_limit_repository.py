"""Tests for canonical risk limit persistence mapping."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.sql import ClauseElement

from pmrp.schemas.risk import RiskLimit, RiskLimitScope
from pmrp.storage import PersistenceTimeoutError
from pmrp.storage.models import RiskLimitRow
from pmrp.storage.repositories import (
    RiskLimitRepository,
    risk_limit_from_row,
    risk_limit_to_row,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


def test_risk_limit_to_row_preserves_canonical_payload() -> None:
    limit = _limit()

    row = risk_limit_to_row(limit)

    assert row.risk_limit_id == "risk_limit_strategy_capital"
    assert row.rule_id == "RISK-STRATEGY-CAPITAL"
    assert row.rule_version == "1.0"
    assert row.scope == "strategy"
    assert row.scope_id == "strat_risk_limit"
    assert row.limit_type == "max_strategy_capital"
    assert row.limit_value == Decimal("1000.00")
    assert row.unit == "USD"
    assert row.effective_at == NOW
    assert row.expires_at == NOW + timedelta(days=1)
    assert row.enabled is True
    assert row.created_by == "operator"
    assert row.approved_by == "risk_manager"


def test_risk_limit_from_row_round_trips_canonical_limit() -> None:
    limit = _limit()
    row = risk_limit_to_row(limit)
    row.aggregate_version = 3
    row.created_at = NOW
    row.updated_at = NOW + timedelta(minutes=1)

    assert risk_limit_from_row(row) == limit


@pytest.mark.asyncio
async def test_repository_add_inserts_row_and_flushes_without_commit() -> None:
    session = _FakeSession()
    repository = RiskLimitRepository(session)  # type: ignore[arg-type]

    await repository.add(_limit())

    assert len(session.added) == 1
    assert isinstance(session.added[0], RiskLimitRow)
    assert session.added[0].limit_value == Decimal("1000.00")
    assert session.flushed == 1
    assert session.committed == 0


@pytest.mark.asyncio
async def test_repository_get_queries_risk_limit_id() -> None:
    row = risk_limit_to_row(_limit())
    session = _FakeSession(results=(row,))
    repository = RiskLimitRepository(session)  # type: ignore[arg-type]

    result = await repository.get("risk_limit_strategy_capital")

    assert result == _limit()
    sql = _compile(session.statements[0])
    assert "risk_limits.risk_limit_id = 'risk_limit_strategy_capital'" in sql


@pytest.mark.asyncio
async def test_repository_get_returns_none_when_missing() -> None:
    session = _FakeSession(results=(None,))
    repository = RiskLimitRepository(session)  # type: ignore[arg-type]

    result = await repository.get("risk_limit_strategy_capital")

    assert result is None


@pytest.mark.asyncio
async def test_repository_list_active_uses_documented_scope_filters() -> None:
    row = risk_limit_to_row(_limit())
    session = _FakeSession(results=((row,),))
    repository = RiskLimitRepository(session)  # type: ignore[arg-type]

    result = await repository.list_active(
        as_of=NOW + timedelta(minutes=5),
        scope=RiskLimitScope.STRATEGY,
        scope_id="strat_risk_limit",
        rule_id="RISK-STRATEGY-CAPITAL",
        limit_type="max_strategy_capital",
        limit=25,
    )

    assert result == (_limit(),)
    sql = _compile(session.statements[0])
    assert "risk_limits.enabled IS true" in sql
    assert "risk_limits.effective_at <= '2026-09-22 12:05:00+00:00'" in sql
    assert "risk_limits.expires_at IS NULL OR pmrp_risk.risk_limits.expires_at >" in sql
    assert "risk_limits.scope = 'strategy'" in sql
    assert "risk_limits.scope_id = 'strat_risk_limit'" in sql
    assert "risk_limits.rule_id = 'RISK-STRATEGY-CAPITAL'" in sql
    assert "risk_limits.limit_type = 'max_strategy_capital'" in sql
    assert "ORDER BY pmrp_risk.risk_limits.scope, pmrp_risk.risk_limits.scope_id" in sql
    assert "LIMIT 25" in sql


@pytest.mark.asyncio
async def test_repository_list_active_rejects_invalid_inputs_before_querying() -> None:
    session = _FakeSession()
    repository = RiskLimitRepository(session)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="limit must be positive"):
        await repository.list_active(as_of=NOW, limit=0)
    with pytest.raises(ValueError, match="scope_id must not be empty"):
        await repository.list_active(as_of=NOW, scope_id="")
    with pytest.raises(ValueError, match="rule_id must not be empty"):
        await repository.list_active(as_of=NOW, rule_id="")
    with pytest.raises(ValueError, match="limit_type must not be empty"):
        await repository.list_active(as_of=NOW, limit_type="")

    assert session.statements == []


@pytest.mark.asyncio
async def test_repository_classifies_sqlalchemy_execute_errors() -> None:
    session = _FakeSession(execute_error=SQLAlchemyTimeoutError("pool exhausted"))
    repository = RiskLimitRepository(session)  # type: ignore[arg-type]

    with pytest.raises(PersistenceTimeoutError, match="timed out"):
        await repository.list_active(as_of=NOW)


@pytest.mark.asyncio
async def test_repository_classifies_flush_errors() -> None:
    session = _FakeSession(flush_error=SQLAlchemyTimeoutError("pool exhausted"))
    repository = RiskLimitRepository(session)  # type: ignore[arg-type]

    with pytest.raises(PersistenceTimeoutError, match="timed out"):
        await repository.add(_limit())


def _limit(**overrides: object) -> RiskLimit:
    payload: dict[str, object] = {
        "risk_limit_id": "risk_limit_strategy_capital",
        "rule_id": "RISK-STRATEGY-CAPITAL",
        "rule_version": "1.0",
        "scope": RiskLimitScope.STRATEGY,
        "scope_id": "strat_risk_limit",
        "limit_type": "max_strategy_capital",
        "limit_value": "1000.00",
        "unit": "USD",
        "effective_at": NOW,
        "expires_at": NOW + timedelta(days=1),
        "enabled": True,
        "created_by": "operator",
        "approved_by": "risk_manager",
    }
    payload.update(overrides)
    return RiskLimit.model_validate(payload)


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
        self.added: list[RiskLimitRow] = []
        self.statements: list[ClauseElement] = []
        self.flushed = 0
        self.committed = 0
        self._results = list(results)
        self._execute_error = execute_error
        self._flush_error = flush_error

    def add(self, row: RiskLimitRow) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        if self._flush_error is not None:
            raise self._flush_error
        self.flushed += 1

    async def execute(self, statement: ClauseElement) -> _FakeResult:
        if self._execute_error is not None:
            raise self._execute_error
        self.statements.append(statement)
        value = self._results.pop(0) if self._results else None
        return _FakeResult(value)


class _FakeResult:
    def __init__(self, value: object) -> None:
        self._value = value

    def scalar_one_or_none(self) -> RiskLimitRow | None:
        if self._value is None:
            return None
        return self._value  # type: ignore[return-value]

    def scalars(self) -> _FakeResult:
        return self

    def all(self) -> list[RiskLimitRow]:
        if self._value is None:
            return []
        if isinstance(self._value, tuple):
            return list(self._value)  # type: ignore[return-value]
        return [self._value]  # type: ignore[list-item]
