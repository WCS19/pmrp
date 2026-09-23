"""Unit tests for risk evaluation event workflow assembly."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import TracebackType
from typing import Literal

import pytest

from pmrp.clock import FrozenClock
from pmrp.events import (
    DeterministicEventIdentifierGenerator,
    EventFactory,
    default_event_type_registry,
)
from pmrp.risk import (
    RiskApprovedOrderRequest,
    RiskBreachFactory,
    RiskBreachPolicy,
    RiskContext,
    RiskEvaluationEventResult,
    RiskEvaluationEventWorkflow,
    RiskEvaluationResult,
    RiskEvaluationService,
    RiskEventFactory,
)
from pmrp.schemas.enums import ExchangeName, OrderType, RiskDecisionStatus, Side, TimeInForce
from pmrp.schemas.events import (
    RISK_APPROVED_EVENT_TYPE,
    RISK_CHECK_REQUESTED_EVENT_TYPE,
    RISK_LIMIT_BREACHED_EVENT_TYPE,
    RISK_REJECTED_EVENT_TYPE,
    RiskApprovedEvent,
    RiskLimitBreachedEvent,
    RiskRejectedEvent,
)
from pmrp.schemas.identifiers import AccountId, ContractId, MarketId, StrategyId
from pmrp.schemas.orders import ApprovedOrder, OrderIntent
from pmrp.schemas.risk import (
    RiskBreach,
    RiskDecision,
    RiskInputSnapshot,
    RiskLimitScope,
    RiskRuleResult,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_risk_workflow")
CONTRACT_ID = ContractId("ctr_risk_workflow")
STRATEGY_ID = StrategyId("strat_risk_workflow")
ACCOUNT_ID = AccountId("acct_01k00000000000000000000000")
INPUT_SNAPSHOT_ID = "risk_input_01k0000000000000000"


async def test_risk_evaluation_event_workflow_builds_approved_events() -> None:
    decision = _decision()
    unit_of_work = _FakeUnitOfWork()
    engine = _FakeEvaluator(decision=decision)
    workflow = RiskEvaluationEventWorkflow(
        service=RiskEvaluationService(engine=engine, unit_of_work_factory=lambda: unit_of_work),
        event_factory=_risk_event_factory(),
    )
    intent = _intent()
    context = RiskContext(evaluated_at=NOW)
    snapshot = _input_snapshot()

    result = await workflow.evaluate_and_build_events(
        intent,
        context,
        snapshot,
        approved_order_request=RiskApprovedOrderRequest(
            exchange=ExchangeName.KALSHI,
            account_id=ACCOUNT_ID,
        ),
    )

    assert result.result.decision == decision
    assert result.result.approved_order is not None
    assert engine.calls == [(intent, context, snapshot.risk_input_snapshot_id)]
    assert unit_of_work.decision_store.added == [decision]
    assert unit_of_work.committed == 1
    assert result.check_requested_event.envelope.event_type == RISK_CHECK_REQUESTED_EVENT_TYPE
    assert result.check_requested_event.input_snapshot == snapshot
    assert len(result.evaluation_events) == 1
    approved_event = result.evaluation_events[0]
    assert isinstance(approved_event, RiskApprovedEvent)
    assert approved_event.envelope.event_type == RISK_APPROVED_EVENT_TYPE
    assert approved_event.decision == decision
    assert approved_event.approved_order == result.result.approved_order
    assert result.all_events == (result.check_requested_event, approved_event)
    assert [event.envelope.event_type for event in result.all_events] == [
        RISK_CHECK_REQUESTED_EVENT_TYPE,
        RISK_APPROVED_EVENT_TYPE,
    ]


async def test_risk_evaluation_event_workflow_builds_rejected_and_breach_events() -> None:
    decision = _rejected_decision()
    unit_of_work = _FakeUnitOfWork()
    workflow = RiskEvaluationEventWorkflow(
        service=RiskEvaluationService(
            engine=_FakeEvaluator(decision=decision),
            unit_of_work_factory=lambda: unit_of_work,
            breach_factory=RiskBreachFactory(
                policies=(
                    RiskBreachPolicy(
                        rule_id="RISK-WORKFLOW",
                        reason_code="RISK_WORKFLOW_REJECTED",
                        scope=RiskLimitScope.STRATEGY,
                        scope_id=str(STRATEGY_ID),
                        severity="critical",
                        action_taken="reject_order",
                    ),
                )
            ),
        ),
        event_factory=_risk_event_factory(),
    )

    result = await workflow.evaluate_and_build_events(
        _intent(),
        RiskContext(evaluated_at=NOW),
        _input_snapshot(),
    )

    assert result.result.decision == decision
    assert result.result.breaches == tuple(unit_of_work.breach_store.added)
    assert len(result.evaluation_events) == 2
    rejected_event = result.evaluation_events[0]
    breach_event = result.evaluation_events[1]
    assert isinstance(rejected_event, RiskRejectedEvent)
    assert rejected_event.envelope.event_type == RISK_REJECTED_EVENT_TYPE
    assert rejected_event.decision == decision
    assert isinstance(breach_event, RiskLimitBreachedEvent)
    assert breach_event.envelope.event_type == RISK_LIMIT_BREACHED_EVENT_TYPE
    assert breach_event.breach == unit_of_work.breach_store.added[0]
    assert result.all_events == (result.check_requested_event, rejected_event, breach_event)
    assert [event.envelope.event_type for event in result.all_events] == [
        RISK_CHECK_REQUESTED_EVENT_TYPE,
        RISK_REJECTED_EVENT_TYPE,
        RISK_LIMIT_BREACHED_EVENT_TYPE,
    ]


async def test_risk_evaluation_event_workflow_rejects_snapshot_lineage_before_service() -> None:
    engine = _FakeEvaluator(decision=_decision())
    workflow = RiskEvaluationEventWorkflow(
        service=RiskEvaluationService(
            engine=engine,
            unit_of_work_factory=lambda: _FakeUnitOfWork(),
        ),
        event_factory=_risk_event_factory(),
    )

    with pytest.raises(ValueError, match="market_id"):
        await workflow.evaluate_and_build_events(
            _intent(),
            RiskContext(evaluated_at=NOW),
            _input_snapshot().model_copy(update={"market_id": "mkt_other"}),
        )

    assert engine.calls == []


def test_risk_evaluation_event_result_validates_event_bundle() -> None:
    event_factory = _risk_event_factory()
    check_event = event_factory.build_check_requested_event(_intent(), _input_snapshot())
    approved_order = ApprovedOrder(
        order_id="ord_01k00000000000000000000000",
        intent_id="intent_risk_workflow",
        strategy_id=STRATEGY_ID,
        risk_decision_id="risk_01k00000000000000000000000",
        exchange=ExchangeName.KALSHI.value,
        account_id=ACCOUNT_ID,
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
        approved_at=NOW,
        approval_expires_at=NOW + timedelta(seconds=2),
        client_order_id="client-risk-workflow",
        idempotency_key="idem-risk-workflow",
        correlation_id="corr_risk_workflow",
    )
    result = RiskEvaluationEventResult(
        result=RiskEvaluationResult(_decision(), approved_order=approved_order),
        check_requested_event=check_event,
        evaluation_events=(event_factory.build_approved_event(_decision(), approved_order),),
    )

    assert result.check_requested_event == check_event
    with pytest.raises(ValueError, match="at least one event"):
        RiskEvaluationEventResult(
            result=result.result,
            check_requested_event=check_event,
            evaluation_events=(),
        )
    with pytest.raises(TypeError, match="risk evaluation events"):
        RiskEvaluationEventResult(
            result=result.result,
            check_requested_event=check_event,
            evaluation_events=(object(),),  # type: ignore[arg-type]
        )


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
        intent_id="intent_risk_workflow",
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
        correlation_id="corr_risk_workflow",
        idempotency_key="idem-risk-workflow",
    )


def _input_snapshot() -> RiskInputSnapshot:
    return RiskInputSnapshot(
        risk_input_snapshot_id=INPUT_SNAPSHOT_ID,
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


def _decision(
    *,
    status: RiskDecisionStatus = RiskDecisionStatus.APPROVED,
    rule_results: tuple[RiskRuleResult, ...] | None = None,
    approved_quantity: Decimal | None = Decimal("10"),
    approved_limit_price: Decimal | None = Decimal("0.50"),
    approval_expires_at: datetime | None = NOW + timedelta(seconds=2),
) -> RiskDecision:
    return RiskDecision(
        risk_decision_id="risk_01k00000000000000000000000",
        intent_id="intent_risk_workflow",
        status=status,
        evaluated_at=NOW,
        input_snapshot_id=INPUT_SNAPSHOT_ID,
        rule_results=rule_results or (_rule_result(),),
        approved_quantity=approved_quantity,
        approved_limit_price=approved_limit_price,
        approval_expires_at=approval_expires_at,
        configuration_hash="sha256:config",
        correlation_id="corr_risk_workflow",
    )


def _rejected_decision() -> RiskDecision:
    return _decision(
        status=RiskDecisionStatus.REJECTED,
        rule_results=(_rule_result(passed=False, reason_code="RISK_WORKFLOW_REJECTED"),),
        approved_quantity=None,
        approved_limit_price=None,
        approval_expires_at=None,
    )


def _rule_result(
    *,
    passed: bool = True,
    reason_code: str = "RISK_WORKFLOW_VALID",
) -> RiskRuleResult:
    return RiskRuleResult(
        rule_id="RISK-WORKFLOW",
        rule_version="1.0",
        passed=passed,
        reason_code=reason_code,
        observed_value=Decimal("1"),
        limit_value=Decimal("2"),
        unit="test",
        evaluated_at=NOW,
    )


class _FakeEvaluator:
    def __init__(self, *, decision: RiskDecision) -> None:
        self._decision = decision
        self.calls: list[tuple[OrderIntent, RiskContext, str]] = []

    async def evaluate(
        self,
        intent: OrderIntent,
        context: RiskContext,
        *,
        input_snapshot_id: str,
    ) -> RiskDecision:
        self.calls.append((intent, context, input_snapshot_id))
        return self._decision


class _FakeDecisionStore:
    def __init__(self) -> None:
        self.added: list[RiskDecision] = []

    async def add(self, decision: RiskDecision) -> None:
        self.added.append(decision)


class _FakeBreachStore:
    def __init__(self) -> None:
        self.added: list[RiskBreach] = []

    async def add(self, breach: RiskBreach) -> None:
        self.added.append(breach)


class _FakeReservationStore:
    async def add(self, reservation: object) -> None:
        del reservation


class _FakeUnitOfWork:
    def __init__(self) -> None:
        self.decision_store = _FakeDecisionStore()
        self.breach_store = _FakeBreachStore()
        self.reservation_store = _FakeReservationStore()
        self.committed = 0

    async def __aenter__(self) -> _FakeUnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        del exc_type, exc, traceback
        return False

    @property
    def risk_decisions(self) -> _FakeDecisionStore:
        return self.decision_store

    @property
    def risk_breaches(self) -> _FakeBreachStore:
        return self.breach_store

    @property
    def capital_reservations(self) -> _FakeReservationStore:
        return self.reservation_store

    async def commit(self) -> None:
        self.committed += 1
