"""Tests for the SQLAlchemy risk unit-of-work adapter."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.schemas.enums import RiskDecisionStatus
from pmrp.schemas.risk import RiskDecision, RiskRuleResult
from pmrp.storage import SqlAlchemyRiskUnitOfWork, UnitOfWorkStateError
from pmrp.storage.models import RiskDecisionRow

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


def test_risk_unit_of_work_rejects_inactive_repository_access() -> None:
    unit_of_work = SqlAlchemyRiskUnitOfWork(session_factory=_SessionFactory(_FakeSession()))

    with pytest.raises(UnitOfWorkStateError, match="not active"):
        _ = unit_of_work.risk_decisions


@pytest.mark.asyncio
async def test_risk_unit_of_work_persists_decision_and_commits() -> None:
    session = _FakeSession()

    async with SqlAlchemyRiskUnitOfWork(
        session_factory=_SessionFactory(session),
    ) as unit_of_work:
        await unit_of_work.risk_decisions.add(_decision())
        await unit_of_work.commit()
        with pytest.raises(UnitOfWorkStateError, match="already finished"):
            _ = unit_of_work.risk_decisions

    assert len(session.added) == 1
    assert isinstance(session.added[0], RiskDecisionRow)
    assert session.flushed == 1
    assert session.committed == 1
    assert session.rolled_back == 0
    assert session.closed == 1


@pytest.mark.asyncio
async def test_risk_unit_of_work_rolls_back_clean_exit_without_commit() -> None:
    session = _FakeSession()

    async with SqlAlchemyRiskUnitOfWork(
        session_factory=_SessionFactory(session),
    ) as unit_of_work:
        await unit_of_work.risk_decisions.add(_decision())

    assert session.flushed == 1
    assert session.committed == 0
    assert session.rolled_back == 1
    assert session.closed == 1


@pytest.mark.asyncio
async def test_risk_unit_of_work_explicit_rollback_finishes_transaction() -> None:
    session = _FakeSession()

    async with SqlAlchemyRiskUnitOfWork(
        session_factory=_SessionFactory(session),
    ) as unit_of_work:
        await unit_of_work.rollback()
        with pytest.raises(UnitOfWorkStateError, match="already finished"):
            _ = unit_of_work.risk_decisions

    assert session.committed == 0
    assert session.rolled_back == 1
    assert session.closed == 1


def _decision() -> RiskDecision:
    return RiskDecision(
        risk_decision_id="risk_01k00000000000000000000000",
        intent_id="intent_risk_uow",
        status=RiskDecisionStatus.APPROVED,
        evaluated_at=NOW,
        input_snapshot_id="risk_input_01k0000000000000000",
        rule_results=(
            RiskRuleResult(
                rule_id="RISK-TEST",
                rule_version="1.0",
                passed=True,
                reason_code="RISK_TEST_VALID",
                reason_text=None,
                observed_value=Decimal("1"),
                limit_value=Decimal("2"),
                unit="test",
                evaluated_at=NOW,
            ),
        ),
        approved_quantity=Decimal("10"),
        approved_limit_price=Decimal("0.50"),
        approval_expires_at=NOW + timedelta(seconds=2),
        configuration_hash="sha256:config",
        correlation_id="corr_risk_uow",
    )


class _SessionFactory:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    def __call__(self) -> _FakeSession:
        return self._session


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[RiskDecisionRow] = []
        self.flushed = 0
        self.committed = 0
        self.rolled_back = 0
        self.closed = 0

    def add(self, row: RiskDecisionRow) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        self.flushed += 1

    async def commit(self) -> None:
        self.committed += 1

    async def rollback(self) -> None:
        self.rolled_back += 1

    async def close(self) -> None:
        self.closed += 1
