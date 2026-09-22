"""Unit tests for deriving approved orders from risk decisions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.risk import (
    ApprovedOrderFactory,
    ApprovedOrderReferences,
    RiskInputError,
    build_approved_order,
)
from pmrp.schemas.enums import OrderType, RiskDecisionStatus, Side, TimeInForce
from pmrp.schemas.identifiers import AccountId, OrderId
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.risk import RiskDecision, RiskRuleResult

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
ACCOUNT_ID = AccountId("acct_approved_order")


def test_approved_order_factory_builds_approved_order_from_decision() -> None:
    intent = _intent()
    decision = _decision()
    factory = ApprovedOrderFactory(reference_generator=_FixedReferences())

    approved_order = factory.build(
        intent,
        decision,
        exchange="kalshi",
        account_id=ACCOUNT_ID,
    )

    assert approved_order.order_id == "ord_fixed_approved"
    assert approved_order.intent_id == intent.intent_id
    assert approved_order.strategy_id == intent.strategy_id
    assert approved_order.risk_decision_id == decision.risk_decision_id
    assert approved_order.exchange == "kalshi"
    assert approved_order.account_id == ACCOUNT_ID
    assert approved_order.market_id == intent.market_id
    assert approved_order.contract_id == intent.contract_id
    assert approved_order.outcome_id == intent.outcome_id
    assert approved_order.side is intent.side
    assert approved_order.quantity == decision.approved_quantity
    assert approved_order.limit_price == decision.approved_limit_price
    assert approved_order.order_type is intent.order_type
    assert approved_order.time_in_force is intent.time_in_force
    assert approved_order.post_only is intent.post_only
    assert approved_order.reduce_only is intent.reduce_only
    assert approved_order.approved_at == decision.evaluated_at
    assert approved_order.approval_expires_at == decision.approval_expires_at
    assert approved_order.client_order_id == "client-fixed-approved"
    assert approved_order.idempotency_key == "idem-fixed-approved"
    assert approved_order.correlation_id == intent.correlation_id


def test_default_approved_order_references_are_deterministic() -> None:
    intent = _intent()
    decision = _decision()

    first = build_approved_order(
        intent,
        decision,
        exchange="kalshi",
        account_id=ACCOUNT_ID,
    )
    second = build_approved_order(
        intent,
        decision,
        exchange="kalshi",
        account_id=ACCOUNT_ID,
    )

    assert first.order_id == second.order_id
    assert first.client_order_id == second.client_order_id
    assert first.idempotency_key == second.idempotency_key
    assert str(first.order_id).startswith("ord_")
    assert first.client_order_id.startswith("pmrp-")
    assert first.idempotency_key.startswith("approved-order-")


def test_default_approved_order_references_change_with_decision() -> None:
    intent = _intent()

    first = build_approved_order(
        intent,
        _decision(risk_decision_id="risk_approved_order_a"),
        exchange="kalshi",
        account_id=ACCOUNT_ID,
    )
    second = build_approved_order(
        intent,
        _decision(risk_decision_id="risk_approved_order_b"),
        exchange="kalshi",
        account_id=ACCOUNT_ID,
    )

    assert first.order_id != second.order_id
    assert first.client_order_id != second.client_order_id
    assert first.idempotency_key != second.idempotency_key


@pytest.mark.parametrize(
    "status",
    [RiskDecisionStatus.REJECTED, RiskDecisionStatus.ERROR],
)
def test_approved_order_factory_rejects_non_approved_decisions(
    status: RiskDecisionStatus,
) -> None:
    decision = _decision(
        status=status,
        rule_results=(_result(passed=False, reason_code=f"RISK_TEST_{status.value}"),),
        approved_quantity=None,
        approved_limit_price=None,
        approval_expires_at=None,
    )

    with pytest.raises(RiskInputError, match="approved risk decision"):
        build_approved_order(
            _intent(),
            decision,
            exchange="kalshi",
            account_id=ACCOUNT_ID,
        )


def test_approved_order_factory_rejects_mismatched_intent_id() -> None:
    with pytest.raises(RiskInputError, match="intent_id"):
        build_approved_order(
            _intent(),
            _decision(intent_id="intent_other_approved_order"),
            exchange="kalshi",
            account_id=ACCOUNT_ID,
        )


def test_approved_order_factory_rejects_mismatched_correlation_id() -> None:
    with pytest.raises(RiskInputError, match="correlation_id"):
        build_approved_order(
            _intent(),
            _decision(correlation_id="corr_other_approved_order"),
            exchange="kalshi",
            account_id=ACCOUNT_ID,
        )


def test_approved_order_factory_rejects_quantity_escalation() -> None:
    with pytest.raises(RiskInputError, match="approved quantity"):
        build_approved_order(
            _intent(),
            _decision(approved_quantity=Decimal("11")),
            exchange="kalshi",
            account_id=ACCOUNT_ID,
        )


def test_approved_order_factory_rejects_empty_exchange() -> None:
    with pytest.raises(RiskInputError, match="exchange"):
        build_approved_order(
            _intent(),
            _decision(),
            exchange="",
            account_id=ACCOUNT_ID,
        )


def _intent() -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_approved_order",
            "strategy_id": "strat_approved_order",
            "market_id": "mkt_approved_order",
            "contract_id": "ctr_approved_order",
            "outcome_id": "out_yes",
            "side": Side.BUY,
            "quantity": "10",
            "limit_price": "0.50",
            "order_type": OrderType.LIMIT,
            "time_in_force": TimeInForce.GTC,
            "post_only": False,
            "reduce_only": False,
            "urgency": "0.50",
            "created_at": NOW,
            "expires_at": NOW + timedelta(seconds=5),
            "signal_ids": (),
            "correlation_id": "corr_approved_order",
            "idempotency_key": "idem-approved-order-intent",
        }
    )


def _decision(
    *,
    risk_decision_id: str = "risk_approved_order",
    intent_id: str = "intent_approved_order",
    status: RiskDecisionStatus = RiskDecisionStatus.APPROVED,
    rule_results: tuple[RiskRuleResult, ...] | None = None,
    approved_quantity: Decimal | None = Decimal("10"),
    approved_limit_price: Decimal | None = Decimal("0.50"),
    approval_expires_at: datetime | None = NOW + timedelta(seconds=2),
    correlation_id: str = "corr_approved_order",
) -> RiskDecision:
    return RiskDecision(
        risk_decision_id=risk_decision_id,
        intent_id=intent_id,
        status=status,
        evaluated_at=NOW,
        input_snapshot_id="risk_input_approved_order",
        rule_results=rule_results or (_result(),),
        approved_quantity=approved_quantity,
        approved_limit_price=approved_limit_price,
        approval_expires_at=approval_expires_at,
        configuration_hash="sha256:config",
        correlation_id=correlation_id,
    )


def _result(*, passed: bool = True, reason_code: str = "RISK_TEST_VALID") -> RiskRuleResult:
    return RiskRuleResult(
        rule_id="RISK-TEST",
        rule_version="1.0",
        passed=passed,
        reason_code=reason_code,
        reason_text=None,
        observed_value=Decimal("1"),
        limit_value=Decimal("2"),
        unit="test",
        evaluated_at=NOW,
    )


class _FixedReferences:
    def references(
        self,
        *,
        intent: OrderIntent,
        decision: RiskDecision,
        exchange: str,
        account_id: AccountId,
    ) -> ApprovedOrderReferences:
        del intent, decision, exchange, account_id
        return ApprovedOrderReferences(
            order_id=OrderId("ord_fixed_approved"),
            client_order_id="client-fixed-approved",
            idempotency_key="idem-fixed-approved",
        )
