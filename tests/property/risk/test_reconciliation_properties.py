"""Property tests for the RISK-018 reconciliation-health rule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.risk import (
    RISK_RECONCILIATION_HEALTH_STATE_FUTURE_REASON,
    RISK_RECONCILIATION_HEALTH_STATE_STALE_REASON,
    RISK_RECONCILIATION_HEALTHY_REASON,
    RISK_RECONCILIATION_MANUAL_REVIEW_REQUIRED_REASON,
    RISK_RECONCILIATION_MISMATCHES_PRESENT_REASON,
    RISK_RECONCILIATION_UNHEALTHY_STATUS_REASON,
    ReconciliationHealthRule,
    RiskContext,
    RiskReconciliationHealthState,
)
from pmrp.schemas.enums import OrderType, Side, TimeInForce
from pmrp.schemas.identifiers import ContractId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.portfolio import ReconciliationStatus

pytestmark = pytest.mark.property

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_risk_reconciliation_health_property")
CONTRACT_ID = ContractId("ctr_risk_reconciliation_health_property")
STRATEGY_ID = StrategyId("strat_risk_reconciliation_health_property")


@given(age_ms=st.integers(min_value=0, max_value=5000))
async def test_reconciliation_health_rule_is_deterministic_when_healthy(age_ms: int) -> None:
    rule = ReconciliationHealthRule(max_state_age=timedelta(milliseconds=5000))
    context = _context(observed_at=NOW - timedelta(milliseconds=age_ms))

    first = await rule.evaluate(_intent(), context)
    second = await rule.evaluate(_intent(), context)

    assert first == second
    assert first.passed is True
    assert first.reason_code == RISK_RECONCILIATION_HEALTHY_REASON
    assert first.observed_value == Decimal("1")
    assert first.limit_value == Decimal("1")


@given(
    status=st.sampled_from(
        [
            ReconciliationStatus.MISMATCH,
            ReconciliationStatus.UNKNOWN,
            ReconciliationStatus.FAILED,
        ]
    )
)
async def test_reconciliation_health_rule_rejects_any_unhealthy_status(
    status: ReconciliationStatus,
) -> None:
    result = await ReconciliationHealthRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(),
        _context(status=status),
    )

    assert result.passed is False
    assert result.reason_code == RISK_RECONCILIATION_UNHEALTHY_STATUS_REASON
    assert result.observed_value == Decimal("0")
    assert result.limit_value == Decimal("1")


@given(manual_review_count=st.integers(min_value=1, max_value=1000))
async def test_reconciliation_health_rule_rejects_any_manual_review_count(
    manual_review_count: int,
) -> None:
    result = await ReconciliationHealthRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(),
        _context(manual_review_count=manual_review_count),
    )

    assert result.passed is False
    assert result.reason_code == RISK_RECONCILIATION_MANUAL_REVIEW_REQUIRED_REASON
    assert result.observed_value == Decimal(manual_review_count)
    assert result.limit_value == Decimal("0")


@given(unresolved_mismatch_count=st.integers(min_value=1, max_value=1000))
async def test_reconciliation_health_rule_rejects_any_unresolved_mismatch_count(
    unresolved_mismatch_count: int,
) -> None:
    result = await ReconciliationHealthRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(),
        _context(unresolved_mismatch_count=unresolved_mismatch_count),
    )

    assert result.passed is False
    assert result.reason_code == RISK_RECONCILIATION_MISMATCHES_PRESENT_REASON
    assert result.observed_value == Decimal(unresolved_mismatch_count)
    assert result.limit_value == Decimal("0")


@given(age_ms=st.integers(min_value=5001, max_value=600000))
async def test_reconciliation_health_rule_rejects_any_stale_state(age_ms: int) -> None:
    result = await ReconciliationHealthRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(),
        _context(observed_at=NOW - timedelta(milliseconds=age_ms)),
    )

    assert result.passed is False
    assert result.reason_code == RISK_RECONCILIATION_HEALTH_STATE_STALE_REASON
    assert result.observed_value == Decimal(age_ms)
    assert result.limit_value == Decimal("5000")


@given(future_ms=st.integers(min_value=1, max_value=600000))
async def test_reconciliation_health_rule_rejects_any_future_state(future_ms: int) -> None:
    result = await ReconciliationHealthRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(),
        _context(observed_at=NOW + timedelta(milliseconds=future_ms)),
    )

    assert result.passed is False
    assert result.reason_code == RISK_RECONCILIATION_HEALTH_STATE_FUTURE_REASON
    assert result.observed_value == Decimal(future_ms)
    assert result.limit_value == Decimal("0")


def _context(
    *,
    status: ReconciliationStatus = ReconciliationStatus.HEALTHY,
    trading_gate_released: bool = True,
    unresolved_mismatch_count: int = 0,
    manual_review_count: int = 0,
    observed_at: datetime = NOW,
) -> RiskContext:
    return RiskContext(
        evaluated_at=NOW,
        reconciliation_health=RiskReconciliationHealthState(
            status=status,
            trading_gate_released=trading_gate_released,
            unresolved_mismatch_count=unresolved_mismatch_count,
            manual_review_count=manual_review_count,
            observed_at=observed_at,
        ),
    )


def _intent() -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_risk_reconciliation_health_property",
            "strategy_id": STRATEGY_ID,
            "market_id": MARKET_ID,
            "contract_id": CONTRACT_ID,
            "outcome_id": "out_yes",
            "side": Side.BUY,
            "quantity": "10",
            "limit_price": "0.50",
            "order_type": OrderType.LIMIT,
            "time_in_force": TimeInForce.GTC,
            "post_only": False,
            "reduce_only": False,
            "urgency": "0.75",
            "created_at": NOW,
            "expires_at": NOW + timedelta(seconds=5),
            "signal_ids": (),
            "correlation_id": "corr_risk_reconciliation_health_property",
            "idempotency_key": "idem-risk-reconciliation-health-property",
        }
    )
