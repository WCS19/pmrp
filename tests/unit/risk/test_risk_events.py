"""Unit tests for canonical risk event builders."""

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
from pmrp.risk import RiskEvaluationResult, RiskEventFactory, build_approved_order
from pmrp.schemas.enums import ExchangeName, OrderType, RiskDecisionStatus, Side, TimeInForce
from pmrp.schemas.events import (
    RISK_APPROVED_EVENT_TYPE,
    RISK_CHECK_REQUESTED_EVENT_TYPE,
    RISK_KILL_SWITCH_ACTIVATED_EVENT_TYPE,
    RISK_KILL_SWITCH_RELEASED_EVENT_TYPE,
    RISK_LIMIT_BREACHED_EVENT_TYPE,
    RISK_REJECTED_EVENT_TYPE,
    KillSwitchActivatedEvent,
    KillSwitchReleasedEvent,
    RiskApprovedEvent,
    RiskLimitBreachedEvent,
    RiskRejectedEvent,
)
from pmrp.schemas.identifiers import AccountId, ContractId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.risk import (
    KillSwitchScope,
    KillSwitchState,
    RiskBreach,
    RiskDecision,
    RiskInputSnapshot,
    RiskLimitScope,
    RiskRuleResult,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_risk_event")
CONTRACT_ID = ContractId("ctr_risk_event")
STRATEGY_ID = StrategyId("strat_risk_event")
ACCOUNT_ID = AccountId("acct_01k00000000000000000000000")
INPUT_SNAPSHOT_ID = "risk_input_01k0000000000000000"


def test_risk_event_factory_builds_check_requested_event_with_lineage() -> None:
    intent = _intent()
    snapshot = _input_snapshot()

    event = _risk_event_factory().build_check_requested_event(intent, snapshot)

    assert event.intent == intent
    assert event.input_snapshot == snapshot
    assert event.envelope.event_type == RISK_CHECK_REQUESTED_EVENT_TYPE
    assert event.envelope.schema_version == 1
    assert event.envelope.producer == "risk"
    assert event.envelope.occurred_at == snapshot.captured_at
    assert event.envelope.published_at == NOW
    assert event.envelope.strategy_id == intent.strategy_id
    assert event.envelope.market_id == intent.market_id
    assert event.envelope.exchange == snapshot.exchange
    assert event.envelope.account_id == snapshot.account_id
    assert event.envelope.correlation_id == intent.correlation_id


def test_risk_event_factory_builds_approved_event_from_evaluation_result() -> None:
    intent = _intent()
    decision = _decision()
    approved_order = build_approved_order(
        intent,
        decision,
        exchange=ExchangeName.KALSHI.value,
        account_id=ACCOUNT_ID,
    )

    events = _risk_event_factory().build_evaluation_events(
        RiskEvaluationResult(decision=decision, approved_order=approved_order)
    )

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, RiskApprovedEvent)
    assert event.envelope.event_type == RISK_APPROVED_EVENT_TYPE
    assert event.envelope.occurred_at == decision.evaluated_at
    assert event.envelope.correlation_id == decision.correlation_id
    assert event.envelope.strategy_id == approved_order.strategy_id
    assert event.envelope.market_id == approved_order.market_id
    assert event.envelope.exchange == approved_order.exchange
    assert event.envelope.account_id == approved_order.account_id
    assert event.envelope.order_id == approved_order.order_id
    assert event.decision == decision
    assert event.approved_order == approved_order


def test_risk_event_factory_builds_rejection_and_breach_events() -> None:
    intent = _intent()
    decision = _rejected_decision()
    breach = _breach(decision)

    events = _risk_event_factory().build_evaluation_events(
        RiskEvaluationResult(decision=decision, breaches=(breach,)),
        intent=intent,
    )

    assert len(events) == 2
    rejected_event = events[0]
    breach_event = events[1]
    assert isinstance(rejected_event, RiskRejectedEvent)
    assert rejected_event.envelope.event_type == RISK_REJECTED_EVENT_TYPE
    assert rejected_event.envelope.occurred_at == decision.evaluated_at
    assert rejected_event.envelope.strategy_id == intent.strategy_id
    assert rejected_event.envelope.market_id == intent.market_id
    assert rejected_event.envelope.correlation_id == decision.correlation_id
    assert rejected_event.decision == decision
    assert isinstance(breach_event, RiskLimitBreachedEvent)
    assert breach_event.envelope.event_type == RISK_LIMIT_BREACHED_EVENT_TYPE
    assert breach_event.envelope.occurred_at == breach.detected_at
    assert breach_event.envelope.correlation_id == breach.correlation_id
    assert breach_event.breach == breach


def test_risk_event_factory_allows_explicit_breach_override() -> None:
    decision = _rejected_decision()
    breach = _breach(decision)

    events = _risk_event_factory().build_evaluation_events(
        RiskEvaluationResult(decision=decision),
        breaches=(breach,),
        intent=_intent(),
    )

    assert len(events) == 2
    assert isinstance(events[1], RiskLimitBreachedEvent)
    assert events[1].breach == breach


def test_risk_event_factory_requires_approved_order_for_approved_result() -> None:
    result = RiskEvaluationResult(decision=_decision())

    with pytest.raises(ValueError, match="approved_order"):
        _risk_event_factory().build_evaluation_events(result)


def test_risk_event_factory_rejects_rejected_intent_lineage_mismatch() -> None:
    mismatched_intent = _intent().model_copy(update={"intent_id": "intent_other"})

    with pytest.raises(ValueError, match="intent_id"):
        _risk_event_factory().build_rejected_event(
            _rejected_decision(),
            intent=mismatched_intent,
        )


def test_risk_event_factory_rejects_unsupported_evaluation_status() -> None:
    result = RiskEvaluationResult(
        decision=_decision(
            status=RiskDecisionStatus.ERROR,
            rule_results=(_rule_result(passed=False, reason_code="RISK_EVENT_ERROR"),),
            approved_quantity=None,
            approved_limit_price=None,
            approval_expires_at=None,
        )
    )

    with pytest.raises(ValueError, match="approved or rejected"):
        _risk_event_factory().build_evaluation_events(result)


def test_risk_event_factory_builds_kill_switch_lifecycle_events() -> None:
    factory = _risk_event_factory()

    activated_event = factory.build_kill_switch_activated_event(_active_kill_switch())
    released_event = factory.build_kill_switch_released_event(_released_kill_switch())

    assert isinstance(activated_event, KillSwitchActivatedEvent)
    assert activated_event.envelope.event_type == RISK_KILL_SWITCH_ACTIVATED_EVENT_TYPE
    assert activated_event.envelope.occurred_at == NOW - timedelta(seconds=5)
    assert activated_event.state.active is True
    assert isinstance(released_event, KillSwitchReleasedEvent)
    assert released_event.envelope.event_type == RISK_KILL_SWITCH_RELEASED_EVENT_TYPE
    assert released_event.envelope.occurred_at == NOW
    assert released_event.state.active is False


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
        intent_id="intent_risk_event",
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
        correlation_id="corr_risk_event",
        idempotency_key="idem-risk-event",
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
        intent_id="intent_risk_event",
        status=status,
        evaluated_at=NOW,
        input_snapshot_id=INPUT_SNAPSHOT_ID,
        rule_results=rule_results or (_rule_result(),),
        approved_quantity=approved_quantity,
        approved_limit_price=approved_limit_price,
        approval_expires_at=approval_expires_at,
        configuration_hash="sha256:config",
        correlation_id="corr_risk_event",
    )


def _rejected_decision() -> RiskDecision:
    return _decision(
        status=RiskDecisionStatus.REJECTED,
        rule_results=(_rule_result(passed=False, reason_code="RISK_EVENT_REJECTED"),),
        approved_quantity=None,
        approved_limit_price=None,
        approval_expires_at=None,
    )


def _rule_result(
    *,
    passed: bool = True,
    reason_code: str = "RISK_EVENT_VALID",
) -> RiskRuleResult:
    return RiskRuleResult(
        rule_id="RISK-EVENT",
        rule_version="1.0",
        passed=passed,
        reason_code=reason_code,
        observed_value=Decimal("1"),
        limit_value=Decimal("2"),
        unit="test",
        evaluated_at=NOW,
    )


def _breach(decision: RiskDecision) -> RiskBreach:
    return RiskBreach(
        breach_id="breach_risk_event",
        rule_id="RISK-EVENT",
        rule_version="1.0",
        scope=RiskLimitScope.STRATEGY,
        scope_id=str(STRATEGY_ID),
        severity="critical",
        detected_at=NOW + timedelta(milliseconds=1),
        observed_value=Decimal("3"),
        limit_value=Decimal("2"),
        unit="test",
        action_taken="reject_order",
        correlation_id=decision.correlation_id,
    )


def _active_kill_switch() -> KillSwitchState:
    return KillSwitchState(
        kill_switch_id="ks_risk_event",
        scope=KillSwitchScope.GLOBAL,
        scope_id=None,
        active=True,
        activated_at=NOW - timedelta(seconds=5),
        activated_by="operator",
        activation_reason="test activation",
        released_at=None,
        released_by=None,
        release_reason=None,
        version=1,
    )


def _released_kill_switch() -> KillSwitchState:
    return KillSwitchState(
        kill_switch_id="ks_risk_event",
        scope=KillSwitchScope.GLOBAL,
        scope_id=None,
        active=False,
        activated_at=NOW - timedelta(seconds=5),
        activated_by="operator",
        activation_reason="test activation",
        released_at=NOW,
        released_by="operator",
        release_reason="test release",
        version=2,
    )
