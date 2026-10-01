"""Tests for the SQLAlchemy risk unit-of-work adapter."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.clock import FrozenClock
from pmrp.events import (
    DeterministicEventIdentifierGenerator,
    EventFactory,
    default_event_type_registry,
)
from pmrp.risk import (
    RiskApprovedOrderRequest,
    RiskContext,
    RiskEvaluationEventUnitOfWork,
    RiskEvaluationEventWorkflow,
    RiskEvaluationService,
    RiskEventFactory,
)
from pmrp.schemas.enums import ExchangeName, OrderType, RiskDecisionStatus, Side, TimeInForce
from pmrp.schemas.events import RISK_APPROVED_EVENT_TYPE, RISK_CHECK_REQUESTED_EVENT_TYPE
from pmrp.schemas.identifiers import AccountId, ContractId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.risk import RiskDecision, RiskInputSnapshot, RiskRuleResult
from pmrp.storage import SqlAlchemyRiskUnitOfWork, UnitOfWorkStateError
from pmrp.storage.models import (
    CanonicalEventRow,
    CapitalReservationRow,
    EventIdRow,
    KillSwitchRow,
    OutboxMessageRow,
    RiskBreachRow,
    RiskDecisionRow,
    RiskLimitRow,
)
from pmrp.storage.repositories import (
    CanonicalEventRepository,
    CapitalReservationRepository,
    KillSwitchRepository,
    OutboxMessageRepository,
    RiskBreachRepository,
    RiskDecisionRepository,
    RiskLimitRepository,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_risk_event_uow")
CONTRACT_ID = ContractId("ctr_risk_event_uow")
STRATEGY_ID = StrategyId("strat_risk_event_uow")
ACCOUNT_ID = AccountId("acct_01k00000000000000000000000")


@pytest.mark.parametrize(
    "repository_attribute",
    [
        "canonical_events",
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
        assert isinstance(unit_of_work.canonical_events, CanonicalEventRepository)
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
async def test_risk_unit_of_work_supports_transactional_event_workflow() -> None:
    session = _FakeSession()
    decision = _decision()
    workflow = RiskEvaluationEventWorkflow(
        service=RiskEvaluationService(
            engine=_FakeEvaluator(decision=decision),
            unit_of_work_factory=lambda: SqlAlchemyRiskUnitOfWork(
                session_factory=_SessionFactory(session),
            ),
        ),
        event_factory=_risk_event_factory(),
    )

    result = await workflow.evaluate_persist_and_build_events(
        _intent(),
        RiskContext(evaluated_at=NOW),
        _input_snapshot(),
        approved_order_request=RiskApprovedOrderRequest(
            exchange=ExchangeName.KALSHI,
            account_id=ACCOUNT_ID,
        ),
    )

    assert result.result.decision == decision
    assert session.committed == 1
    assert session.rolled_back == 0
    assert session.closed == 1
    assert session.flushed == 3

    assert isinstance(session.added[0], RiskDecisionRow)
    assert session.added[0].risk_decision_id == str(decision.risk_decision_id)
    event_id_rows = [row for row in session.added if isinstance(row, EventIdRow)]
    canonical_rows = [row for row in session.added if isinstance(row, CanonicalEventRow)]
    outbox_rows = [row for row in session.added if isinstance(row, OutboxMessageRow)]
    assert [row.event_id for row in event_id_rows] == [
        str(event.envelope.event_id) for event in result.all_events
    ]
    assert [row.event_type for row in canonical_rows] == [
        RISK_CHECK_REQUESTED_EVENT_TYPE,
        RISK_APPROVED_EVENT_TYPE,
    ]
    assert [row.event_id for row in canonical_rows] == [row.event_id for row in outbox_rows]
    assert [row.payload["envelope"]["event_type"] for row in outbox_rows] == [
        RISK_CHECK_REQUESTED_EVENT_TYPE,
        RISK_APPROVED_EVENT_TYPE,
    ]


@pytest.mark.asyncio
async def test_risk_unit_of_work_conforms_to_event_workflow_protocol() -> None:
    async with SqlAlchemyRiskUnitOfWork(
        session_factory=_SessionFactory(_FakeSession()),
    ) as unit_of_work:
        assert isinstance(unit_of_work, RiskEvaluationEventUnitOfWork)


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


def _risk_event_factory() -> RiskEventFactory:
    return RiskEventFactory(
        event_factory=EventFactory(
            clock=FrozenClock(NOW),
            registry=default_event_type_registry(),
            identifier_generator=DeterministicEventIdentifierGenerator(),
        )
    )


def _intent() -> OrderIntent:
    return OrderIntent(
        intent_id="intent_risk_uow",
        strategy_id=STRATEGY_ID,
        market_id=MARKET_ID,
        contract_id=CONTRACT_ID,
        outcome_id="out_yes",
        side=Side.BUY,
        quantity=Decimal("10"),
        limit_price=Decimal("0.50"),
        order_type=OrderType.LIMIT,
        time_in_force=TimeInForce.GTC,
        post_only=False,
        reduce_only=False,
        urgency=Decimal("0.50"),
        created_at=NOW - timedelta(seconds=2),
        expires_at=NOW + timedelta(seconds=5),
        signal_ids=(),
        correlation_id="corr_risk_uow",
        idempotency_key="idem-risk-uow",
    )


def _input_snapshot() -> RiskInputSnapshot:
    return RiskInputSnapshot(
        risk_input_snapshot_id="risk_input_01k0000000000000000",
        captured_at=NOW - timedelta(seconds=1),
        strategy_id=STRATEGY_ID,
        exchange=ExchangeName.KALSHI.value,
        account_id=ACCOUNT_ID,
        market_id=MARKET_ID,
        current_position=Decimal("2"),
        open_order_quantity=Decimal("3"),
        available_balance=Decimal("100.00"),
        gross_exposure=Decimal("40.00"),
        net_exposure=Decimal("25.00"),
        daily_realized_pnl=Decimal("1.00"),
        daily_unrealized_pnl=Decimal("-0.25"),
        market_data_age_ms=250,
        reconciliation_healthy=True,
        kill_switch_clear=True,
    )


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
        "canonical_events",
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
            CanonicalEventRow
            | CapitalReservationRow
            | EventIdRow
            | KillSwitchRow
            | OutboxMessageRow
            | RiskBreachRow
            | RiskDecisionRow
            | RiskLimitRow
        ] = []
        self.flushed = 0
        self.committed = 0
        self.rolled_back = 0
        self.closed = 0

    def add(
        self,
        row: CanonicalEventRow
        | CapitalReservationRow
        | EventIdRow
        | KillSwitchRow
        | OutboxMessageRow
        | RiskBreachRow
        | RiskDecisionRow
        | RiskLimitRow,
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


class _FakeEvaluator:
    def __init__(self, *, decision: RiskDecision) -> None:
        self._decision = decision

    async def evaluate(
        self,
        intent: OrderIntent,
        context: RiskContext,
        *,
        input_snapshot_id: str,
    ) -> RiskDecision:
        del context
        assert intent.intent_id == self._decision.intent_id
        assert input_snapshot_id == self._decision.input_snapshot_id
        return self._decision
