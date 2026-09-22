"""Property tests for the RISK-020 arbitrage-leg risk rule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.risk import (
    RISK_ARBITRAGE_HEDGE_TIMEOUT_EXPIRED_REASON,
    RISK_ARBITRAGE_LEG_EXPOSURE_ABOVE_MAX_REASON,
    RISK_ARBITRAGE_LEG_STATE_FUTURE_REASON,
    RISK_ARBITRAGE_LEG_STATE_STALE_REASON,
    RISK_ARBITRAGE_LEG_VALID_REASON,
    ArbitrageLegRiskRule,
    RiskArbitrageLegState,
    RiskContext,
)
from pmrp.schemas.enums import OrderType, Side, TimeInForce
from pmrp.schemas.identifiers import ContractId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent

pytestmark = pytest.mark.property

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_risk_arbitrage_leg_property")
CONTRACT_ID = ContractId("ctr_risk_arbitrage_leg_property")
STRATEGY_ID = StrategyId("strat_risk_arbitrage_leg_property")


@st.composite
def _valid_quantity_pair(draw: st.DrawFn) -> tuple[Decimal, Decimal]:
    max_quantity = draw(st.integers(min_value=0, max_value=1000))
    current_quantity = draw(st.integers(min_value=0, max_value=max_quantity))
    return Decimal(current_quantity), Decimal(max_quantity)


@given(quantity_pair=_valid_quantity_pair(), age_ms=st.integers(0, 5000))
async def test_arbitrage_leg_risk_rule_allows_any_quantity_at_or_below_cap(
    quantity_pair: tuple[Decimal, Decimal],
    age_ms: int,
) -> None:
    current_quantity, max_quantity = quantity_pair
    result = await ArbitrageLegRiskRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(),
        _context(
            current_unhedged_quantity=current_quantity,
            max_unhedged_quantity=max_quantity,
            hedge_deadline_at=NOW + timedelta(seconds=10) if current_quantity > 0 else None,
            observed_at=NOW - timedelta(milliseconds=age_ms),
        ),
    )

    assert result.passed is True
    assert result.reason_code == RISK_ARBITRAGE_LEG_VALID_REASON
    assert result.observed_value == current_quantity
    assert result.limit_value == max_quantity


@given(max_quantity=st.integers(min_value=0, max_value=1000))
async def test_arbitrage_leg_risk_rule_rejects_any_quantity_above_cap(
    max_quantity: int,
) -> None:
    current_quantity = Decimal(max_quantity + 1)
    result = await ArbitrageLegRiskRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(),
        _context(
            current_unhedged_quantity=current_quantity,
            max_unhedged_quantity=Decimal(max_quantity),
            hedge_deadline_at=NOW + timedelta(seconds=10),
            observed_at=NOW,
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ARBITRAGE_LEG_EXPOSURE_ABOVE_MAX_REASON
    assert result.observed_value == current_quantity
    assert result.limit_value == Decimal(max_quantity)


@given(age_ms=st.integers(min_value=5001, max_value=600000))
async def test_arbitrage_leg_risk_rule_rejects_any_stale_state(age_ms: int) -> None:
    result = await ArbitrageLegRiskRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(),
        _context(
            current_unhedged_quantity=Decimal("0"),
            max_unhedged_quantity=Decimal("5"),
            observed_at=NOW - timedelta(milliseconds=age_ms),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ARBITRAGE_LEG_STATE_STALE_REASON
    assert result.observed_value == Decimal(age_ms)
    assert result.limit_value == Decimal("5000")


@given(future_ms=st.integers(min_value=1, max_value=600000))
async def test_arbitrage_leg_risk_rule_rejects_any_future_state(future_ms: int) -> None:
    result = await ArbitrageLegRiskRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(),
        _context(
            current_unhedged_quantity=Decimal("0"),
            max_unhedged_quantity=Decimal("5"),
            observed_at=NOW + timedelta(milliseconds=future_ms),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ARBITRAGE_LEG_STATE_FUTURE_REASON
    assert result.observed_value == Decimal(future_ms)
    assert result.limit_value == Decimal("0")


@given(overdue_ms=st.integers(min_value=1, max_value=600000))
async def test_arbitrage_leg_risk_rule_rejects_any_expired_hedge_timeout(
    overdue_ms: int,
) -> None:
    result = await ArbitrageLegRiskRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(),
        _context(
            current_unhedged_quantity=Decimal("1"),
            max_unhedged_quantity=Decimal("5"),
            hedge_deadline_at=NOW - timedelta(milliseconds=overdue_ms),
            observed_at=NOW,
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ARBITRAGE_HEDGE_TIMEOUT_EXPIRED_REASON
    assert result.observed_value == Decimal(overdue_ms)
    assert result.limit_value == Decimal("0")


def _context(
    *,
    current_unhedged_quantity: Decimal,
    max_unhedged_quantity: Decimal,
    observed_at: datetime,
    hedge_deadline_at: datetime | None = None,
) -> RiskContext:
    return RiskContext(
        evaluated_at=NOW,
        arbitrage_leg=RiskArbitrageLegState(
            current_unhedged_quantity=current_unhedged_quantity,
            max_unhedged_quantity=max_unhedged_quantity,
            hedge_deadline_at=hedge_deadline_at,
            observed_at=observed_at,
        ),
    )


def _intent() -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_risk_arbitrage_leg_property",
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
            "correlation_id": "corr_risk_arbitrage_leg_property",
            "idempotency_key": "idem-risk-arbitrage-leg-property",
        }
    )
