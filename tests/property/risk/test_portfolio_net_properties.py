"""Property tests for the RISK-011 portfolio net-exposure limit rule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.risk import (
    RISK_PORTFOLIO_NET_ABOVE_MAX_REASON,
    RISK_PORTFOLIO_NET_STATE_FUTURE_REASON,
    RISK_PORTFOLIO_NET_STATE_STALE_REASON,
    RISK_PORTFOLIO_NET_VALID_REASON,
    PortfolioNetLimitRule,
    RiskContext,
    RiskPortfolioNetExposureState,
)
from pmrp.schemas.enums import OrderType, Side, TimeInForce
from pmrp.schemas.identifiers import ContractId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent

pytestmark = pytest.mark.property

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_risk_portfolio_net_property")
CONTRACT_ID = ContractId("ctr_risk_portfolio_net_property")
STRATEGY_ID = StrategyId("strat_risk_portfolio_net_property")
CENT = Decimal("0.01")


@given(
    current_dollars=st.integers(min_value=0, max_value=1000),
    quantity=st.integers(min_value=1, max_value=100),
    price_cents=st.integers(min_value=1, max_value=100),
)
async def test_portfolio_net_limit_rule_is_deterministic_at_exact_long_cap(
    current_dollars: int,
    quantity: int,
    price_cents: int,
) -> None:
    price = Decimal(price_cents) / Decimal("100")
    projected_exposure = Decimal(current_dollars) + Decimal(quantity) * price
    rule = PortfolioNetLimitRule(max_state_age=timedelta(milliseconds=5000))
    context = _context(
        current_net_exposure=Decimal(current_dollars),
        max_net_exposure=projected_exposure,
        observed_at=NOW,
    )

    first = await rule.evaluate(
        _intent(quantity=str(quantity), limit_price=str(price), side=Side.BUY), context
    )
    second = await rule.evaluate(
        _intent(quantity=str(quantity), limit_price=str(price), side=Side.BUY), context
    )

    assert first == second
    assert first.passed is True
    assert first.reason_code == RISK_PORTFOLIO_NET_VALID_REASON
    assert first.observed_value == projected_exposure
    assert first.limit_value == projected_exposure


@given(
    current_dollars=st.integers(min_value=0, max_value=1000),
    quantity=st.integers(min_value=1, max_value=100),
    price_cents=st.integers(min_value=1, max_value=100),
)
async def test_portfolio_net_limit_rule_rejects_any_buy_above_long_cap(
    current_dollars: int,
    quantity: int,
    price_cents: int,
) -> None:
    price = Decimal(price_cents) / Decimal("100")
    projected_exposure = Decimal(current_dollars) + Decimal(quantity) * price
    cap = projected_exposure - CENT
    if cap <= Decimal("0"):
        cap = Decimal("0.0001")
        price = cap + CENT
        quantity = 1
        projected_exposure = price

    result = await PortfolioNetLimitRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(quantity=str(quantity), limit_price=str(price), side=Side.BUY),
        _context(
            current_net_exposure=Decimal(current_dollars),
            max_net_exposure=cap,
            observed_at=NOW,
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_PORTFOLIO_NET_ABOVE_MAX_REASON
    assert result.observed_value == projected_exposure
    assert result.limit_value == cap


@given(
    current_short_dollars=st.integers(min_value=0, max_value=1000),
    quantity=st.integers(min_value=1, max_value=100),
    price_cents=st.integers(min_value=1, max_value=100),
)
async def test_portfolio_net_limit_rule_rejects_any_sell_above_short_cap(
    current_short_dollars: int,
    quantity: int,
    price_cents: int,
) -> None:
    price = Decimal(price_cents) / Decimal("100")
    projected_magnitude = Decimal(current_short_dollars) + Decimal(quantity) * price
    cap = projected_magnitude - CENT
    if cap <= Decimal("0"):
        cap = Decimal("0.0001")
        price = cap + CENT
        quantity = 1
        projected_magnitude = price

    result = await PortfolioNetLimitRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(quantity=str(quantity), limit_price=str(price), side=Side.SELL),
        _context(
            current_net_exposure=-Decimal(current_short_dollars),
            max_net_exposure=cap,
            observed_at=NOW,
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_PORTFOLIO_NET_ABOVE_MAX_REASON
    assert result.observed_value == projected_magnitude
    assert result.limit_value == cap


@given(
    current_dollars=st.integers(min_value=-1000, max_value=1000),
    open_order_dollars=st.integers(min_value=-1000, max_value=1000),
    reserved_dollars=st.integers(min_value=-1000, max_value=1000),
    quantity=st.integers(min_value=1, max_value=100),
    price_cents=st.integers(min_value=1, max_value=100),
)
async def test_portfolio_net_limit_rule_includes_pending_deltas_at_exact_cap(
    current_dollars: int,
    open_order_dollars: int,
    reserved_dollars: int,
    quantity: int,
    price_cents: int,
) -> None:
    price = Decimal(price_cents) / Decimal("100")
    projected_exposure = (
        Decimal(current_dollars)
        + Decimal(open_order_dollars)
        + Decimal(reserved_dollars)
        + Decimal(quantity) * price
    )
    cap = max(abs(projected_exposure), Decimal("0.1"))

    result = await PortfolioNetLimitRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(quantity=str(quantity), limit_price=str(price), side=Side.BUY),
        _context(
            current_net_exposure=Decimal(current_dollars),
            open_order_net_exposure_delta=Decimal(open_order_dollars),
            reserved_net_exposure_delta=Decimal(reserved_dollars),
            max_net_exposure=cap,
            observed_at=NOW,
        ),
    )

    assert result.passed is True
    assert result.reason_code == RISK_PORTFOLIO_NET_VALID_REASON
    assert result.observed_value == abs(projected_exposure)
    assert result.limit_value == cap


@given(age_ms=st.integers(min_value=5001, max_value=600000))
async def test_portfolio_net_limit_rule_rejects_any_stale_exposure_state(age_ms: int) -> None:
    result = await PortfolioNetLimitRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(quantity="10", limit_price="0.50", side=Side.BUY),
        _context(
            current_net_exposure=Decimal("3"),
            max_net_exposure=Decimal("10"),
            observed_at=NOW - timedelta(milliseconds=age_ms),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_PORTFOLIO_NET_STATE_STALE_REASON
    assert result.observed_value == Decimal(age_ms)
    assert result.limit_value == Decimal("5000")


@given(future_ms=st.integers(min_value=1, max_value=600000))
async def test_portfolio_net_limit_rule_rejects_any_future_exposure_state(
    future_ms: int,
) -> None:
    result = await PortfolioNetLimitRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(quantity="10", limit_price="0.50", side=Side.BUY),
        _context(
            current_net_exposure=Decimal("3"),
            max_net_exposure=Decimal("10"),
            observed_at=NOW + timedelta(milliseconds=future_ms),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_PORTFOLIO_NET_STATE_FUTURE_REASON
    assert result.observed_value == Decimal(future_ms)
    assert result.limit_value == Decimal("0")


def _context(
    *,
    current_net_exposure: Decimal,
    max_net_exposure: Decimal,
    observed_at: datetime,
    open_order_net_exposure_delta: Decimal = Decimal("0"),
    reserved_net_exposure_delta: Decimal = Decimal("0"),
) -> RiskContext:
    return RiskContext(
        evaluated_at=NOW,
        portfolio_net_exposure=RiskPortfolioNetExposureState(
            current_net_exposure=current_net_exposure,
            open_order_net_exposure_delta=open_order_net_exposure_delta,
            reserved_net_exposure_delta=reserved_net_exposure_delta,
            max_net_exposure=max_net_exposure,
            observed_at=observed_at,
        ),
    )


def _intent(*, quantity: str, limit_price: str, side: Side) -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_risk_portfolio_net_property",
            "strategy_id": STRATEGY_ID,
            "market_id": MARKET_ID,
            "contract_id": CONTRACT_ID,
            "outcome_id": "out_yes",
            "side": side,
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
            "correlation_id": "corr_risk_portfolio_net_property",
            "idempotency_key": "idem-risk-portfolio-net-property",
        }
    )
