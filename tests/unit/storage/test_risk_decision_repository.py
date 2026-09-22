"""Tests for canonical risk decision persistence mapping."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.sql import Select

from pmrp.schemas.enums import RiskDecisionStatus
from pmrp.schemas.risk import RiskDecision, RiskRuleResult
from pmrp.schemas.serialization import canonical_sha256
from pmrp.storage import InvariantViolationError, PersistenceTimeoutError
from pmrp.storage.models import RiskDecisionRow
from pmrp.storage.repositories import (
    RiskDecisionRepository,
    risk_decision_from_row,
    risk_decision_to_row,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


def test_risk_decision_to_row_serializes_canonical_payload() -> None:
    decision = _decision()

    row = risk_decision_to_row(decision)

    assert row.evaluated_at == decision.evaluated_at
    assert row.risk_decision_id == "risk_01k00000000000000000000000"
    assert row.intent_id == "intent_01k00000000000000000000000"
    assert row.status == "approved"
    assert row.input_snapshot_id == "risk_input_01k0000000000000000"
    assert row.approved_quantity == Decimal("10")
    assert row.approved_limit_price == Decimal("0.42")
    assert row.approval_expires_at == NOW + timedelta(seconds=2)
    assert row.configuration_hash == "sha256:config"
    assert row.correlation_id == "corr_01k00000000000000000000000"
    assert row.rule_results == [
        {
            "evaluated_at": "2026-09-22T12:00:00Z",
            "limit_value": "5000",
            "observed_value": "12",
            "passed": True,
            "reason_code": "MARKET_DATA_FRESH",
            "reason_text": None,
            "rule_id": "RISK-TEST-001",
            "rule_version": "1.0",
            "unit": "milliseconds",
        }
    ]
    assert row.payload_hash == canonical_sha256(decision)


def test_risk_decision_from_row_round_trips_canonical_decision() -> None:
    decision = _decision()
    row = risk_decision_to_row(decision)

    assert risk_decision_from_row(row) == decision


def test_risk_decision_from_row_rejects_payload_hash_mismatch() -> None:
    row = risk_decision_to_row(_decision())
    row.payload_hash = "sha256:tampered"

    with pytest.raises(InvariantViolationError, match="payload hash mismatch") as exc_info:
        risk_decision_from_row(row)

    assert exc_info.value.context == {"risk_decision_id": "risk_01k00000000000000000000000"}


@pytest.mark.asyncio
async def test_repository_add_inserts_row_and_flushes_without_commit() -> None:
    session = _FakeSession()
    repository = RiskDecisionRepository(session)  # type: ignore[arg-type]
    decision = _decision()

    await repository.add(decision)

    assert len(session.added) == 1
    assert isinstance(session.added[0], RiskDecisionRow)
    assert session.added[0].payload_hash == canonical_sha256(decision)
    assert session.flushed == 1
    assert session.committed == 0


@pytest.mark.asyncio
async def test_repository_add_classifies_sqlalchemy_flush_errors() -> None:
    session = _FakeSession(flush_error=SQLAlchemyTimeoutError("pool exhausted"))
    repository = RiskDecisionRepository(session)  # type: ignore[arg-type]

    with pytest.raises(PersistenceTimeoutError, match="timed out"):
        await repository.add(_decision())


@pytest.mark.asyncio
async def test_repository_get_by_key_queries_partition_key_and_decision_id() -> None:
    row = risk_decision_to_row(_decision())
    session = _FakeSession(execute_rows=(row,))
    repository = RiskDecisionRepository(session)  # type: ignore[arg-type]

    result = await repository.get_by_key(
        evaluated_at=NOW,
        risk_decision_id="risk_01k00000000000000000000000",  # type: ignore[arg-type]
    )

    assert result == _decision()
    sql = _compile(session.statements[0])
    assert "risk_decisions.evaluated_at = '2026-09-22 12:00:00+00:00'" in sql
    assert "risk_decisions.risk_decision_id = 'risk_01k00000000000000000000000'" in sql


@pytest.mark.asyncio
async def test_repository_get_by_key_returns_none_when_missing() -> None:
    session = _FakeSession(execute_rows=(None,))
    repository = RiskDecisionRepository(session)  # type: ignore[arg-type]

    result = await repository.get_by_key(
        evaluated_at=NOW,
        risk_decision_id="risk_01k00000000000000000000000",  # type: ignore[arg-type]
    )

    assert result is None


@pytest.mark.asyncio
async def test_repository_get_latest_for_intent_uses_documented_query_path() -> None:
    row = risk_decision_to_row(_decision())
    session = _FakeSession(execute_rows=(row,))
    repository = RiskDecisionRepository(session)  # type: ignore[arg-type]

    result = await repository.get_latest_for_intent(
        "intent_01k00000000000000000000000"  # type: ignore[arg-type]
    )

    assert result == _decision()
    sql = _compile(session.statements[0])
    assert "risk_decisions.intent_id = 'intent_01k00000000000000000000000'" in sql
    assert "ORDER BY pmrp_risk.risk_decisions.evaluated_at DESC" in sql
    assert "LIMIT 1" in sql


@pytest.mark.asyncio
async def test_repository_get_classifies_sqlalchemy_execute_errors() -> None:
    session = _FakeSession(execute_error=SQLAlchemyTimeoutError("pool exhausted"))
    repository = RiskDecisionRepository(session)  # type: ignore[arg-type]

    with pytest.raises(PersistenceTimeoutError, match="timed out"):
        await repository.get_latest_for_intent(
            "intent_01k00000000000000000000000"  # type: ignore[arg-type]
        )


def _decision() -> RiskDecision:
    return RiskDecision(
        risk_decision_id="risk_01k00000000000000000000000",
        intent_id="intent_01k00000000000000000000000",
        status=RiskDecisionStatus.APPROVED,
        evaluated_at=NOW,
        input_snapshot_id="risk_input_01k0000000000000000",
        rule_results=(
            RiskRuleResult(
                rule_id="RISK-TEST-001",
                rule_version="1.0",
                passed=True,
                reason_code="MARKET_DATA_FRESH",
                reason_text=None,
                observed_value=Decimal("12"),
                limit_value=Decimal("5000"),
                unit="milliseconds",
                evaluated_at=NOW,
            ),
        ),
        approved_quantity=Decimal("10"),
        approved_limit_price=Decimal("0.42"),
        approval_expires_at=NOW + timedelta(seconds=2),
        configuration_hash="sha256:config",
        correlation_id="corr_01k00000000000000000000000",
    )


def _compile(statement: Select[Any]) -> str:
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
        execute_rows: tuple[RiskDecisionRow | None, ...] = (),
        flush_error: Exception | None = None,
        execute_error: Exception | None = None,
    ) -> None:
        self.added: list[RiskDecisionRow] = []
        self.statements: list[Select[Any]] = []
        self.flushed = 0
        self.committed = 0
        self._execute_rows = list(execute_rows)
        self._flush_error = flush_error
        self._execute_error = execute_error

    def add(self, row: RiskDecisionRow) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        if self._flush_error is not None:
            raise self._flush_error
        self.flushed += 1

    async def execute(self, statement: Select[Any]) -> _FakeResult:
        if self._execute_error is not None:
            raise self._execute_error
        self.statements.append(statement)
        row = self._execute_rows.pop(0) if self._execute_rows else None
        return _FakeResult(row)


class _FakeResult:
    def __init__(self, row: RiskDecisionRow | None) -> None:
        self._row = row

    def scalar_one_or_none(self) -> RiskDecisionRow | None:
        return self._row
