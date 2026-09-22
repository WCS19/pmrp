"""Property tests for the RISK-013 exchange-capital limit rule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.risk import (
    RISK_EXCHANGE_CAPITAL_ABOVE_MAX_REASON,
    RISK_EXCHANGE_CAPITAL_STATE_FUTURE_REASON,
    RISK_EXCHANGE_CAPITAL_STATE_STALE_REASON,
    RISK_EXCHANGE_CAPITAL_VALID_REASON,
    ExchangeCapitalLimitRule,
    RiskContext,
    RiskExchangeCapitalState,
)
from pmrp.schemas.enums import OrderType, Side, TimeInForce
from pmrp.schemas.identifiers import ContractId, ExchangeId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent

pytestmark = pytest.mark.property

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
EXCHANGE_ID = ExchangeId("xchg_risk_exchange_capital_property")
MARKET_ID = MarketId("mkt_risk_exchange_capital_property")
CONTRACT_ID = ContractId("ctr_risk_exchange_capital_property")
STRATEGY_ID = StrategyId("strat_risk_exchange_capital_property")
CENT = Decimal("0.01")


@given(
    current_dollars=st.integers(min_value=0, max_value=1000),
    quantity=st.integers(min_value=1, max_value=100),
    price_cents=st.integers(min_value=1, max_value=100),
)
async def test_exchange_capital_limit_rule_is_deterministic_at_exact_cap(
    current_dollars: int,
    quantity: int,
    price_cents: int,
) -> None:
    price = Decimal(price_cents) / Decimal("100")
    order_capital = Decimal(quantity) * price
    max_exchange_capital = Decimal(current_dollars) + order_capital
    rule = ExchangeCapitalLimitRule(max_state_age=timedelta(milliseconds=5000))
    context = _context(
        current_capital_used=Decimal(current_dollars),
        max_exchange_capital=max_exchange_capital,
        observed_at=NOW,
    )

    first = await rule.evaluate(_intent(quantity=str(quantity), limit_price=str(price)), context)
    second = await rule.evaluate(_intent(quantity=str(quantity), limit_price=str(price)), context)

    assert first == second
    assert first.passed is True
    assert first.reason_code == RISK_EXCHANGE_CAPITAL_VALID_REASON
    assert first.observed_value == max_exchange_capital
    assert first.limit_value == max_exchange_capital


@given(
    current_dollars=st.integers(min_value=0, max_value=1000),
    quantity=st.integers(min_value=1, max_value=100),
    price_cents=st.integers(min_value=1, max_value=100),
)
async def test_exchange_capital_limit_rule_rejects_any_capital_above_cap(
    current_dollars: int,
    quantity: int,
    price_cents: int,
) -> None:
    price = Decimal(price_cents) / Decimal("100")
    projected_capital = Decimal(current_dollars) + Decimal(quantity) * price
    cap = projected_capital - CENT
    if cap <= Decimal("0"):
        cap = Decimal("0.0001")
        price = cap + CENT
        quantity = 1
        projected_capital = price

    result = await ExchangeCapitalLimitRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(quantity=str(quantity), limit_price=str(price)),
        _context(
            current_capital_used=Decimal(current_dollars),
            max_exchange_capital=cap,
            observed_at=NOW,
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_EXCHANGE_CAPITAL_ABOVE_MAX_REASON
    assert result.observed_value == projected_capital
    assert result.limit_value == cap


@given(
    current_dollars=st.integers(min_value=0, max_value=1000),
    open_order_dollars=st.integers(min_value=0, max_value=1000),
    reserved_dollars=st.integers(min_value=0, max_value=1000),
    quantity=st.integers(min_value=1, max_value=100),
    price_cents=st.integers(min_value=1, max_value=100),
)
async def test_exchange_capital_limit_rule_includes_pending_capital_at_exact_cap(
    current_dollars: int,
    open_order_dollars: int,
    reserved_dollars: int,
    quantity: int,
    price_cents: int,
) -> None:
    price = Decimal(price_cents) / Decimal("100")
    projected_capital = (
        Decimal(current_dollars)
        + Decimal(open_order_dollars)
        + Decimal(reserved_dollars)
        + Decimal(quantity) * price
    )

    result = await ExchangeCapitalLimitRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(quantity=str(quantity), limit_price=str(price)),
        _context(
            current_capital_used=Decimal(current_dollars),
            open_order_capital=Decimal(open_order_dollars),
            reserved_capital=Decimal(reserved_dollars),
            max_exchange_capital=projected_capital,
            observed_at=NOW,
        ),
    )

    assert result.passed is True
    assert result.reason_code == RISK_EXCHANGE_CAPITAL_VALID_REASON
    assert result.observed_value == projected_capital
    assert result.limit_value == projected_capital


@given(age_ms=st.integers(min_value=5001, max_value=600000))
async def test_exchange_capital_limit_rule_rejects_any_stale_capital_state(age_ms: int) -> None:
    result = await ExchangeCapitalLimitRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(quantity="10", limit_price="0.50"),
        _context(
            current_capital_used=Decimal("15"),
            max_exchange_capital=Decimal("25"),
            observed_at=NOW - timedelta(milliseconds=age_ms),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_EXCHANGE_CAPITAL_STATE_STALE_REASON
    assert result.observed_value == Decimal(age_ms)
    assert result.limit_value == Decimal("5000")


@given(future_ms=st.integers(min_value=1, max_value=600000))
async def test_exchange_capital_limit_rule_rejects_any_future_capital_state(
    future_ms: int,
) -> None:
    result = await ExchangeCapitalLimitRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(quantity="10", limit_price="0.50"),
        _context(
            current_capital_used=Decimal("15"),
            max_exchange_capital=Decimal("25"),
            observed_at=NOW + timedelta(milliseconds=future_ms),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_EXCHANGE_CAPITAL_STATE_FUTURE_REASON
    assert result.observed_value == Decimal(future_ms)
    assert result.limit_value == Decimal("0")


def _context(
    *,
    current_capital_used: Decimal,
    max_exchange_capital: Decimal,
    observed_at: datetime,
    open_order_capital: Decimal = Decimal("0"),
    reserved_capital: Decimal = Decimal("0"),
) -> RiskContext:
    return RiskContext(
        evaluated_at=NOW,
        market_exchanges={MARKET_ID: EXCHANGE_ID},
        exchange_capital={
            EXCHANGE_ID: RiskExchangeCapitalState(
                current_capital_used=current_capital_used,
                open_order_capital=open_order_capital,
                reserved_capital=reserved_capital,
                max_exchange_capital=max_exchange_capital,
                observed_at=observed_at,
            )
        },
    )


def _intent(*, quantity: str, limit_price: str) -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_risk_exchange_capital_property",
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
            "correlation_id": "corr_risk_exchange_capital_property",
            "idempotency_key": "idem-risk-exchange-capital-property",
        }
    )
