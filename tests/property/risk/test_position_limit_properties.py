"""Property tests for the RISK-009 market-position limit rule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.risk import (
    RISK_MARKET_POSITION_ABOVE_MAX_REASON,
    RISK_MARKET_POSITION_STATE_FUTURE_REASON,
    RISK_MARKET_POSITION_STATE_STALE_REASON,
    RISK_MARKET_POSITION_VALID_REASON,
    MarketPositionLimitRule,
    RiskContext,
    RiskMarketPositionState,
)
from pmrp.schemas.enums import OrderType, Side, TimeInForce
from pmrp.schemas.identifiers import ContractId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent

pytestmark = pytest.mark.property

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_risk_position_limit_property")
CONTRACT_ID = ContractId("ctr_risk_position_limit_property")
STRATEGY_ID = StrategyId("strat_risk_position_limit_property")


@given(
    current_position=st.integers(min_value=0, max_value=100),
    quantity=st.integers(min_value=1, max_value=100),
)
async def test_market_position_limit_rule_is_deterministic_at_exact_long_cap(
    current_position: int,
    quantity: int,
) -> None:
    max_position = Decimal(current_position + quantity)
    rule = MarketPositionLimitRule(max_state_age=timedelta(milliseconds=5000))
    context = _context(
        current_position=Decimal(current_position),
        max_position=max_position,
        observed_at=NOW,
    )

    first = await rule.evaluate(_intent(quantity=str(quantity), side=Side.BUY), context)
    second = await rule.evaluate(_intent(quantity=str(quantity), side=Side.BUY), context)

    assert first == second
    assert first.passed is True
    assert first.reason_code == RISK_MARKET_POSITION_VALID_REASON
    assert first.observed_value == max_position
    assert first.limit_value == max_position


@given(
    current_position=st.integers(min_value=0, max_value=100),
    quantity=st.integers(min_value=1, max_value=100),
)
async def test_market_position_limit_rule_rejects_any_buy_above_cap(
    current_position: int,
    quantity: int,
) -> None:
    max_position = Decimal(current_position + quantity - 1)
    if max_position <= Decimal("0"):
        max_position = Decimal("0.5")

    result = await MarketPositionLimitRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(quantity=str(quantity), side=Side.BUY),
        _context(
            current_position=Decimal(current_position),
            max_position=max_position,
            observed_at=NOW,
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_MARKET_POSITION_ABOVE_MAX_REASON
    assert result.observed_value == Decimal(current_position + quantity)
    assert result.limit_value == max_position


@given(
    current_short=st.integers(min_value=0, max_value=100),
    quantity=st.integers(min_value=1, max_value=100),
)
async def test_market_position_limit_rule_rejects_any_sell_above_short_cap(
    current_short: int,
    quantity: int,
) -> None:
    projected_magnitude = Decimal(current_short + quantity)
    max_position = projected_magnitude - Decimal("1")
    if max_position <= Decimal("0"):
        max_position = Decimal("0.5")

    result = await MarketPositionLimitRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(quantity=str(quantity), side=Side.SELL),
        _context(
            current_position=-Decimal(current_short),
            max_position=max_position,
            observed_at=NOW,
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_MARKET_POSITION_ABOVE_MAX_REASON
    assert result.observed_value == projected_magnitude
    assert result.limit_value == max_position


@given(
    current_position=st.integers(min_value=-100, max_value=100),
    open_delta=st.integers(min_value=-100, max_value=100),
    reserved_delta=st.integers(min_value=-100, max_value=100),
    quantity=st.integers(min_value=1, max_value=100),
)
async def test_market_position_limit_rule_includes_pending_deltas_at_exact_cap(
    current_position: int,
    open_delta: int,
    reserved_delta: int,
    quantity: int,
) -> None:
    projected_position = Decimal(current_position + open_delta + reserved_delta + quantity)
    max_position = max(abs(projected_position), Decimal("0.1"))

    result = await MarketPositionLimitRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(quantity=str(quantity), side=Side.BUY),
        _context(
            current_position=Decimal(current_position),
            open_order_position_delta=Decimal(open_delta),
            reserved_position_delta=Decimal(reserved_delta),
            max_position=max_position,
            observed_at=NOW,
        ),
    )

    assert result.passed is True
    assert result.reason_code == RISK_MARKET_POSITION_VALID_REASON
    assert result.observed_value == abs(projected_position)
    assert result.limit_value == max_position


@given(age_ms=st.integers(min_value=5001, max_value=600000))
async def test_market_position_limit_rule_rejects_any_stale_position_state(age_ms: int) -> None:
    result = await MarketPositionLimitRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(quantity="2", side=Side.BUY),
        _context(
            current_position=Decimal("3"),
            max_position=Decimal("10"),
            observed_at=NOW - timedelta(milliseconds=age_ms),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_MARKET_POSITION_STATE_STALE_REASON
    assert result.observed_value == Decimal(age_ms)
    assert result.limit_value == Decimal("5000")


@given(future_ms=st.integers(min_value=1, max_value=600000))
async def test_market_position_limit_rule_rejects_any_future_position_state(
    future_ms: int,
) -> None:
    result = await MarketPositionLimitRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(quantity="2", side=Side.BUY),
        _context(
            current_position=Decimal("3"),
            max_position=Decimal("10"),
            observed_at=NOW + timedelta(milliseconds=future_ms),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_MARKET_POSITION_STATE_FUTURE_REASON
    assert result.observed_value == Decimal(future_ms)
    assert result.limit_value == Decimal("0")


def _context(
    *,
    current_position: Decimal,
    max_position: Decimal,
    observed_at: datetime,
    open_order_position_delta: Decimal = Decimal("0"),
    reserved_position_delta: Decimal = Decimal("0"),
) -> RiskContext:
    return RiskContext(
        evaluated_at=NOW,
        market_positions={
            MARKET_ID: RiskMarketPositionState(
                current_position=current_position,
                open_order_position_delta=open_order_position_delta,
                reserved_position_delta=reserved_position_delta,
                max_position=max_position,
                observed_at=observed_at,
            )
        },
    )


def _intent(*, quantity: str, side: Side) -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_risk_position_limit_property",
            "strategy_id": STRATEGY_ID,
            "market_id": MARKET_ID,
            "contract_id": CONTRACT_ID,
            "outcome_id": "out_yes",
            "side": side,
            "quantity": quantity,
            "limit_price": "0.50",
            "order_type": OrderType.LIMIT,
            "time_in_force": TimeInForce.GTC,
            "post_only": False,
            "reduce_only": False,
            "urgency": "0.75",
            "created_at": NOW,
            "expires_at": NOW + timedelta(seconds=5),
            "signal_ids": (),
            "correlation_id": "corr_risk_position_limit_property",
            "idempotency_key": "idem-risk-position-limit-property",
        }
    )
