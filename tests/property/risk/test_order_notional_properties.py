"""Property tests for the RISK-008 order-notional limit rule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.risk import (
    RISK_ORDER_NOTIONAL_ABOVE_MAX_REASON,
    RISK_ORDER_NOTIONAL_LIMIT_FUTURE_REASON,
    RISK_ORDER_NOTIONAL_LIMIT_STALE_REASON,
    RISK_ORDER_NOTIONAL_VALID_REASON,
    OrderNotionalLimitRule,
    RiskContext,
    RiskNotionalLimitState,
)
from pmrp.schemas.enums import OrderType, Side, TimeInForce
from pmrp.schemas.identifiers import ContractId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent

pytestmark = pytest.mark.property

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_risk_order_notional_property")
CONTRACT_ID = ContractId("ctr_risk_order_notional_property")
STRATEGY_ID = StrategyId("strat_risk_order_notional_property")
CENT = Decimal("0.01")


@given(
    quantity=st.integers(min_value=1, max_value=100),
    price_cents=st.integers(min_value=1, max_value=100),
)
async def test_order_notional_limit_rule_is_deterministic_at_exact_cap(
    quantity: int,
    price_cents: int,
) -> None:
    price = Decimal(price_cents) / Decimal("100")
    expected_notional = Decimal(quantity) * price
    rule = OrderNotionalLimitRule(max_state_age=timedelta(milliseconds=5000))
    context = _context(max_notional=expected_notional, observed_at=NOW)

    first = await rule.evaluate(_intent(quantity=str(quantity), limit_price=str(price)), context)
    second = await rule.evaluate(_intent(quantity=str(quantity), limit_price=str(price)), context)

    assert first == second
    assert first.passed is True
    assert first.reason_code == RISK_ORDER_NOTIONAL_VALID_REASON
    assert first.observed_value == expected_notional
    assert first.limit_value == expected_notional


@given(
    quantity=st.integers(min_value=1, max_value=100),
    price_cents=st.integers(min_value=1, max_value=100),
)
async def test_order_notional_limit_rule_rejects_any_notional_above_cap(
    quantity: int,
    price_cents: int,
) -> None:
    price = Decimal(price_cents) / Decimal("100")
    expected_notional = Decimal(quantity) * price
    cap = expected_notional - CENT
    if cap <= Decimal("0"):
        cap = Decimal("0.0001")
        price = cap + CENT
        quantity = 1
        expected_notional = price

    result = await OrderNotionalLimitRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(quantity=str(quantity), limit_price=str(price)),
        _context(max_notional=cap, observed_at=NOW),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ORDER_NOTIONAL_ABOVE_MAX_REASON
    assert result.observed_value == expected_notional
    assert result.limit_value == cap


@given(age_ms=st.integers(min_value=5001, max_value=600000))
async def test_order_notional_limit_rule_rejects_any_stale_limit(age_ms: int) -> None:
    result = await OrderNotionalLimitRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(quantity="10", limit_price="0.43"),
        _context(max_notional=Decimal("5"), observed_at=NOW - timedelta(milliseconds=age_ms)),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ORDER_NOTIONAL_LIMIT_STALE_REASON
    assert result.observed_value == Decimal(age_ms)
    assert result.limit_value == Decimal("5000")


@given(future_ms=st.integers(min_value=1, max_value=600000))
async def test_order_notional_limit_rule_rejects_any_future_limit(future_ms: int) -> None:
    result = await OrderNotionalLimitRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(quantity="10", limit_price="0.43"),
        _context(max_notional=Decimal("5"), observed_at=NOW + timedelta(milliseconds=future_ms)),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ORDER_NOTIONAL_LIMIT_FUTURE_REASON
    assert result.observed_value == Decimal(future_ms)
    assert result.limit_value == Decimal("0")


def _context(*, max_notional: Decimal, observed_at: datetime) -> RiskContext:
    return RiskContext(
        evaluated_at=NOW,
        notional_limits={
            CONTRACT_ID: RiskNotionalLimitState(
                max_notional=max_notional,
                observed_at=observed_at,
            )
        },
    )


def _intent(*, quantity: str, limit_price: str) -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_risk_order_notional_property",
            "strategy_id": STRATEGY_ID,
            "market_id": MARKET_ID,
            "contract_id": CONTRACT_ID,
            "outcome_id": "out_yes",
            "side": Side.BUY,
            "quantity": quantity,
            "limit_price": limit_price,
            "order_type": OrderType.LIMIT,
            "time_in_force": TimeInForce.GTC,
            "post_only": False,
            "reduce_only": False,
            "urgency": "0.75",
            "created_at": NOW,
            "expires_at": NOW + timedelta(seconds=5),
            "signal_ids": (),
            "correlation_id": "corr_risk_order_notional_property",
            "idempotency_key": "idem-risk-order-notional-property",
        }
    )
