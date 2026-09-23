"""Tests for the SQLAlchemy risk unit-of-work adapter."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.schemas.enums import RiskDecisionStatus
from pmrp.schemas.risk import RiskDecision, RiskRuleResult
from pmrp.storage import SqlAlchemyRiskUnitOfWork, UnitOfWorkStateError
from pmrp.storage.models import (
    CapitalReservationRow,
    KillSwitchRow,
    RiskBreachRow,
    RiskDecisionRow,
    RiskLimitRow,
)
from pmrp.storage.repositories import (
    CapitalReservationRepository,
    KillSwitchRepository,
    OutboxMessageRepository,
    RiskBreachRepository,
    RiskDecisionRepository,
    RiskLimitRepository,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "repository_attribute",
    [
        "capital_reservations",
        "kill_switches",
        "outbox_messages",
        "risk_breaches",
        "risk_decisions",
        "risk_limits",
    ],
)
def test_risk_unit_of_work_rejects_inactive_repository_access(
    repository_attribute: str,
) -> None:
    unit_of_work = SqlAlchemyRiskUnitOfWork(session_factory=_SessionFactory(_FakeSession()))

    with pytest.raises(UnitOfWorkStateError, match="not active"):
        _ = getattr(unit_of_work, repository_attribute)


@pytest.mark.asyncio
async def test_risk_unit_of_work_exposes_repositories_during_active_transaction() -> None:
    async with SqlAlchemyRiskUnitOfWork(
        session_factory=_SessionFactory(_FakeSession()),
    ) as unit_of_work:
        assert isinstance(unit_of_work.capital_reservations, CapitalReservationRepository)
        assert isinstance(unit_of_work.kill_switches, KillSwitchRepository)
        assert isinstance(unit_of_work.outbox_messages, OutboxMessageRepository)
        assert isinstance(unit_of_work.risk_breaches, RiskBreachRepository)
        assert isinstance(unit_of_work.risk_decisions, RiskDecisionRepository)
        assert isinstance(unit_of_work.risk_limits, RiskLimitRepository)


@pytest.mark.asyncio
async def test_risk_unit_of_work_persists_decision_and_commits() -> None:
    session = _FakeSession()

    async with SqlAlchemyRiskUnitOfWork(
        session_factory=_SessionFactory(session),
    ) as unit_of_work:
        await unit_of_work.risk_decisions.add(_decision())
        await unit_of_work.commit()
        _assert_repositories_reject_after_finished(unit_of_work)

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
        _assert_repositories_reject_after_finished(unit_of_work)

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


def _assert_repositories_reject_after_finished(
    unit_of_work: SqlAlchemyRiskUnitOfWork,
) -> None:
    for repository_attribute in (
        "capital_reservations",
        "kill_switches",
        "outbox_messages",
        "risk_breaches",
        "risk_decisions",
        "risk_limits",
    ):
        with pytest.raises(UnitOfWorkStateError, match="already finished"):
            _ = getattr(unit_of_work, repository_attribute)


class _SessionFactory:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    def __call__(self) -> _FakeSession:
        return self._session


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[
            CapitalReservationRow | KillSwitchRow | RiskBreachRow | RiskDecisionRow | RiskLimitRow
        ] = []
        self.flushed = 0
        self.committed = 0
        self.rolled_back = 0
        self.closed = 0

    def add(
        self,
        row: CapitalReservationRow | KillSwitchRow | RiskBreachRow | RiskDecisionRow | RiskLimitRow,
    ) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        self.flushed += 1

    async def commit(self) -> None:
        self.committed += 1

    async def rollback(self) -> None:
        self.rolled_back += 1

    async def close(self) -> None:
        self.closed += 1
