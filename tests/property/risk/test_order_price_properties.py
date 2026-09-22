"""Property tests for the RISK-006 order-price validation rule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.risk import (
    RISK_ORDER_PRICE_ABOVE_MAX_REASON,
    RISK_ORDER_PRICE_BELOW_MIN_REASON,
    RISK_ORDER_PRICE_BOUNDS_FUTURE_REASON,
    RISK_ORDER_PRICE_BOUNDS_STALE_REASON,
    RISK_ORDER_PRICE_OFF_TICK_REASON,
    RISK_ORDER_PRICE_VALID_REASON,
    OrderPriceValidRule,
    RiskContext,
    RiskPriceBoundsState,
)
from pmrp.schemas.enums import OrderType, Side, TimeInForce
from pmrp.schemas.identifiers import MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent

pytestmark = pytest.mark.property

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_risk_order_price_property")
STRATEGY_ID = StrategyId("strat_risk_order_price_property")


@given(cents=st.integers(min_value=0, max_value=100))
async def test_order_price_valid_rule_is_deterministic_for_valid_cents(cents: int) -> None:
    price = Decimal(cents) / Decimal("100")
    rule = OrderPriceValidRule(max_state_age=timedelta(milliseconds=5000))
    context = _context(
        min_price=Decimal("0"),
        max_price=Decimal("1"),
        tick_size=Decimal("0.01"),
        observed_at=NOW,
    )

    first = await rule.evaluate(_intent(limit_price=str(price)), context)
    second = await rule.evaluate(_intent(limit_price=str(price)), context)

    assert first == second
    assert first.passed is True
    assert first.reason_code == RISK_ORDER_PRICE_VALID_REASON
    assert first.observed_value == price
    assert first.limit_value == Decimal("1")


@given(cents=st.integers(min_value=0, max_value=9))
async def test_order_price_valid_rule_rejects_any_price_below_min(cents: int) -> None:
    price = Decimal(cents) / Decimal("100")
    result = await OrderPriceValidRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(limit_price=str(price)),
        _context(
            min_price=Decimal("0.10"),
            max_price=Decimal("0.90"),
            observed_at=NOW,
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ORDER_PRICE_BELOW_MIN_REASON
    assert result.observed_value == price
    assert result.limit_value == Decimal("0.10")


@given(cents=st.integers(min_value=91, max_value=200))
async def test_order_price_valid_rule_rejects_any_price_above_max(cents: int) -> None:
    price = Decimal(cents) / Decimal("100")
    result = await OrderPriceValidRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(limit_price=str(price)),
        _context(
            min_price=Decimal("0.10"),
            max_price=Decimal("0.90"),
            observed_at=NOW,
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ORDER_PRICE_ABOVE_MAX_REASON
    assert result.observed_value == price
    assert result.limit_value == Decimal("0.90")


@given(cents=st.integers(min_value=1, max_value=99).filter(lambda value: value % 5 != 0))
async def test_order_price_valid_rule_rejects_any_off_tick_cent_price(cents: int) -> None:
    price = Decimal(cents) / Decimal("100")
    result = await OrderPriceValidRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(limit_price=str(price)),
        _context(
            min_price=Decimal("0"),
            max_price=Decimal("1"),
            tick_size=Decimal("0.05"),
            observed_at=NOW,
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ORDER_PRICE_OFF_TICK_REASON
    assert result.observed_value == price
    assert result.limit_value == Decimal("0.05")


@given(age_ms=st.integers(min_value=5001, max_value=600000))
async def test_order_price_valid_rule_rejects_any_stale_bounds(age_ms: int) -> None:
    result = await OrderPriceValidRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(limit_price="0.43"),
        _context(
            min_price=Decimal("0"),
            max_price=Decimal("1"),
            observed_at=NOW - timedelta(milliseconds=age_ms),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ORDER_PRICE_BOUNDS_STALE_REASON
    assert result.observed_value == Decimal(age_ms)
    assert result.limit_value == Decimal("5000")


@given(future_ms=st.integers(min_value=1, max_value=600000))
async def test_order_price_valid_rule_rejects_any_future_bounds(future_ms: int) -> None:
    result = await OrderPriceValidRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(limit_price="0.43"),
        _context(
            min_price=Decimal("0"),
            max_price=Decimal("1"),
            observed_at=NOW + timedelta(milliseconds=future_ms),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ORDER_PRICE_BOUNDS_FUTURE_REASON
    assert result.observed_value == Decimal(future_ms)
    assert result.limit_value == Decimal("0")


def _context(
    *,
    min_price: Decimal,
    max_price: Decimal,
    observed_at: datetime,
    tick_size: Decimal | None = None,
) -> RiskContext:
    return RiskContext(
        evaluated_at=NOW,
        price_bounds={
            MARKET_ID: RiskPriceBoundsState(
                min_price=min_price,
                max_price=max_price,
                tick_size=tick_size,
                observed_at=observed_at,
            )
        },
    )


def _intent(*, limit_price: str) -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_risk_order_price_property",
            "strategy_id": STRATEGY_ID,
            "market_id": MARKET_ID,
            "contract_id": "ctr_risk_order_price_property",
            "outcome_id": "out_yes",
            "side": Side.BUY,
            "quantity": "10",
            "limit_price": limit_price,
            "order_type": OrderType.LIMIT,
            "time_in_force": TimeInForce.GTC,
            "post_only": False,
            "reduce_only": False,
            "urgency": "0.75",
            "created_at": NOW,
            "expires_at": NOW + timedelta(seconds=5),
            "signal_ids": (),
            "correlation_id": "corr_risk_order_price_property",
            "idempotency_key": "idem-risk-order-price-property",
        }
    )
