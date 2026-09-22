"""Property tests for the RISK-015 open-order limit rule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.risk import (
    RISK_OPEN_ORDER_LIMIT_ABOVE_MAX_REASON,
    RISK_OPEN_ORDER_LIMIT_STATE_FUTURE_REASON,
    RISK_OPEN_ORDER_LIMIT_STATE_STALE_REASON,
    RISK_OPEN_ORDER_LIMIT_VALID_REASON,
    OpenOrderLimitRule,
    RiskContext,
    RiskOpenOrderLimitState,
)
from pmrp.schemas.enums import OrderType, Side, TimeInForce
from pmrp.schemas.identifiers import ContractId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent

pytestmark = pytest.mark.property

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_risk_open_order_limit_property")
CONTRACT_ID = ContractId("ctr_risk_open_order_limit_property")
STRATEGY_ID = StrategyId("strat_risk_open_order_limit_property")


@given(projected_count=st.integers(min_value=1, max_value=1000))
async def test_open_order_limit_rule_is_deterministic_at_exact_cap(
    projected_count: int,
) -> None:
    rule = OpenOrderLimitRule(max_state_age=timedelta(milliseconds=5000))
    context = _context(
        current_open_orders=projected_count - 1,
        max_open_orders=projected_count,
        observed_at=NOW,
    )

    first = await rule.evaluate(_intent(), context)
    second = await rule.evaluate(_intent(), context)

    assert first == second
    assert first.passed is True
    assert first.reason_code == RISK_OPEN_ORDER_LIMIT_VALID_REASON
    assert first.observed_value == Decimal(projected_count)
    assert first.limit_value == Decimal(projected_count)


@given(
    current_open_orders=st.integers(min_value=1, max_value=1000),
    excess_orders=st.integers(min_value=1, max_value=1000),
)
async def test_open_order_limit_rule_rejects_any_count_above_cap(
    current_open_orders: int,
    excess_orders: int,
) -> None:
    projected_count = current_open_orders + 1
    cap = max(1, projected_count - excess_orders)

    result = await OpenOrderLimitRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(),
        _context(
            current_open_orders=current_open_orders,
            max_open_orders=cap,
            observed_at=NOW,
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_OPEN_ORDER_LIMIT_ABOVE_MAX_REASON
    assert result.observed_value == Decimal(projected_count)
    assert result.limit_value == Decimal(cap)


@given(
    current_open_orders=st.integers(min_value=0, max_value=1000),
    pending_cancel_orders=st.integers(min_value=0, max_value=1000),
    reserved_open_orders=st.integers(min_value=0, max_value=1000),
)
async def test_open_order_limit_rule_includes_pending_and_reserved_counts_at_exact_cap(
    current_open_orders: int,
    pending_cancel_orders: int,
    reserved_open_orders: int,
) -> None:
    projected_count = current_open_orders + pending_cancel_orders + reserved_open_orders + 1

    result = await OpenOrderLimitRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(),
        _context(
            current_open_orders=current_open_orders,
            pending_cancel_orders=pending_cancel_orders,
            reserved_open_orders=reserved_open_orders,
            max_open_orders=projected_count,
            observed_at=NOW,
        ),
    )

    assert result.passed is True
    assert result.reason_code == RISK_OPEN_ORDER_LIMIT_VALID_REASON
    assert result.observed_value == Decimal(projected_count)
    assert result.limit_value == Decimal(projected_count)


@given(age_ms=st.integers(min_value=5001, max_value=600000))
async def test_open_order_limit_rule_rejects_any_stale_open_order_state(age_ms: int) -> None:
    result = await OpenOrderLimitRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(),
        _context(
            current_open_orders=8,
            max_open_orders=10,
            observed_at=NOW - timedelta(milliseconds=age_ms),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_OPEN_ORDER_LIMIT_STATE_STALE_REASON
    assert result.observed_value == Decimal(age_ms)
    assert result.limit_value == Decimal("5000")


@given(future_ms=st.integers(min_value=1, max_value=600000))
async def test_open_order_limit_rule_rejects_any_future_open_order_state(
    future_ms: int,
) -> None:
    result = await OpenOrderLimitRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(),
        _context(
            current_open_orders=8,
            max_open_orders=10,
            observed_at=NOW + timedelta(milliseconds=future_ms),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_OPEN_ORDER_LIMIT_STATE_FUTURE_REASON
    assert result.observed_value == Decimal(future_ms)
    assert result.limit_value == Decimal("0")


def _context(
    *,
    current_open_orders: int,
    max_open_orders: int,
    observed_at: datetime,
    pending_cancel_orders: int = 0,
    reserved_open_orders: int = 0,
) -> RiskContext:
    return RiskContext(
        evaluated_at=NOW,
        open_order_limit=RiskOpenOrderLimitState(
            current_open_orders=current_open_orders,
            pending_cancel_orders=pending_cancel_orders,
            reserved_open_orders=reserved_open_orders,
            max_open_orders=max_open_orders,
            observed_at=observed_at,
        ),
    )


def _intent() -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_risk_open_order_limit_property",
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
            "correlation_id": "corr_risk_open_order_limit_property",
            "idempotency_key": "idem-risk-open-order-limit-property",
        }
    )
