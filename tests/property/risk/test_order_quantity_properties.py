"""Property tests for the RISK-007 order-quantity limit rule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.risk import (
    RISK_ORDER_QUANTITY_ABOVE_MAX_REASON,
    RISK_ORDER_QUANTITY_BELOW_MIN_REASON,
    RISK_ORDER_QUANTITY_LIMITS_FUTURE_REASON,
    RISK_ORDER_QUANTITY_LIMITS_STALE_REASON,
    RISK_ORDER_QUANTITY_OFF_INCREMENT_REASON,
    RISK_ORDER_QUANTITY_VALID_REASON,
    OrderQuantityLimitRule,
    RiskContext,
    RiskQuantityLimitsState,
)
from pmrp.schemas.enums import OrderType, Side, TimeInForce
from pmrp.schemas.identifiers import ContractId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent

pytestmark = pytest.mark.property

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_risk_order_quantity_property")
CONTRACT_ID = ContractId("ctr_risk_order_quantity_property")
STRATEGY_ID = StrategyId("strat_risk_order_quantity_property")


@given(units=st.integers(min_value=0, max_value=20))
async def test_order_quantity_limit_rule_is_deterministic_for_valid_increments(
    units: int,
) -> None:
    quantity = Decimal("5") + Decimal(units * 5)
    rule = OrderQuantityLimitRule(max_state_age=timedelta(milliseconds=5000))
    context = _context(
        min_quantity=Decimal("5"),
        max_quantity=Decimal("105"),
        quantity_increment=Decimal("5"),
        observed_at=NOW,
    )

    first = await rule.evaluate(_intent(quantity=str(quantity)), context)
    second = await rule.evaluate(_intent(quantity=str(quantity)), context)

    assert first == second
    assert first.passed is True
    assert first.reason_code == RISK_ORDER_QUANTITY_VALID_REASON
    assert first.observed_value == quantity
    assert first.limit_value == Decimal("105")


@given(quantity=st.integers(min_value=1, max_value=4))
async def test_order_quantity_limit_rule_rejects_any_quantity_below_min(quantity: int) -> None:
    result = await OrderQuantityLimitRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(quantity=str(quantity)),
        _context(
            min_quantity=Decimal("5"),
            max_quantity=Decimal("105"),
            quantity_increment=Decimal("1"),
            observed_at=NOW,
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ORDER_QUANTITY_BELOW_MIN_REASON
    assert result.observed_value == Decimal(quantity)
    assert result.limit_value == Decimal("5")


@given(quantity=st.integers(min_value=106, max_value=500))
async def test_order_quantity_limit_rule_rejects_any_quantity_above_max(quantity: int) -> None:
    result = await OrderQuantityLimitRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(quantity=str(quantity)),
        _context(
            min_quantity=Decimal("5"),
            max_quantity=Decimal("105"),
            quantity_increment=Decimal("1"),
            observed_at=NOW,
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ORDER_QUANTITY_ABOVE_MAX_REASON
    assert result.observed_value == Decimal(quantity)
    assert result.limit_value == Decimal("105")


@given(quantity=st.integers(min_value=6, max_value=104).filter(lambda value: (value - 5) % 5 != 0))
async def test_order_quantity_limit_rule_rejects_any_off_increment_quantity(
    quantity: int,
) -> None:
    result = await OrderQuantityLimitRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(quantity=str(quantity)),
        _context(
            min_quantity=Decimal("5"),
            max_quantity=Decimal("105"),
            quantity_increment=Decimal("5"),
            observed_at=NOW,
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ORDER_QUANTITY_OFF_INCREMENT_REASON
    assert result.observed_value == Decimal(quantity)
    assert result.limit_value == Decimal("5")


@given(age_ms=st.integers(min_value=5001, max_value=600000))
async def test_order_quantity_limit_rule_rejects_any_stale_limits(age_ms: int) -> None:
    result = await OrderQuantityLimitRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(quantity="10"),
        _context(
            min_quantity=Decimal("1"),
            max_quantity=Decimal("100"),
            quantity_increment=Decimal("1"),
            observed_at=NOW - timedelta(milliseconds=age_ms),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ORDER_QUANTITY_LIMITS_STALE_REASON
    assert result.observed_value == Decimal(age_ms)
    assert result.limit_value == Decimal("5000")


@given(future_ms=st.integers(min_value=1, max_value=600000))
async def test_order_quantity_limit_rule_rejects_any_future_limits(future_ms: int) -> None:
    result = await OrderQuantityLimitRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(quantity="10"),
        _context(
            min_quantity=Decimal("1"),
            max_quantity=Decimal("100"),
            quantity_increment=Decimal("1"),
            observed_at=NOW + timedelta(milliseconds=future_ms),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ORDER_QUANTITY_LIMITS_FUTURE_REASON
    assert result.observed_value == Decimal(future_ms)
    assert result.limit_value == Decimal("0")


def _context(
    *,
    min_quantity: Decimal,
    max_quantity: Decimal,
    quantity_increment: Decimal,
    observed_at: datetime,
) -> RiskContext:
    return RiskContext(
        evaluated_at=NOW,
        quantity_limits={
            CONTRACT_ID: RiskQuantityLimitsState(
                min_quantity=min_quantity,
                max_quantity=max_quantity,
                quantity_increment=quantity_increment,
                observed_at=observed_at,
            )
        },
    )


def _intent(*, quantity: str) -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_risk_order_quantity_property",
            "strategy_id": STRATEGY_ID,
            "market_id": MARKET_ID,
            "contract_id": CONTRACT_ID,
            "outcome_id": "out_yes",
            "side": Side.BUY,
            "quantity": quantity,
            "limit_price": "0.43",
            "order_type": OrderType.LIMIT,
            "time_in_force": TimeInForce.GTC,
            "post_only": False,
            "reduce_only": False,
            "urgency": "0.75",
            "created_at": NOW,
            "expires_at": NOW + timedelta(seconds=5),
            "signal_ids": (),
            "correlation_id": "corr_risk_order_quantity_property",
            "idempotency_key": "idem-risk-order-quantity-property",
        }
    )
