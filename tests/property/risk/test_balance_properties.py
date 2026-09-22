"""Property tests for the RISK-017 available-balance rule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.risk import (
    RISK_AVAILABLE_BALANCE_INSUFFICIENT_REASON,
    RISK_AVAILABLE_BALANCE_STATE_FUTURE_REASON,
    RISK_AVAILABLE_BALANCE_STATE_STALE_REASON,
    RISK_AVAILABLE_BALANCE_VALID_REASON,
    AvailableBalanceRule,
    RiskAvailableBalanceState,
    RiskContext,
)
from pmrp.schemas.enums import OrderType, Side, TimeInForce
from pmrp.schemas.identifiers import ContractId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent

pytestmark = pytest.mark.property

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_risk_available_balance_property")
CONTRACT_ID = ContractId("ctr_risk_available_balance_property")
STRATEGY_ID = StrategyId("strat_risk_available_balance_property")


@given(required_balance=st.integers(min_value=1, max_value=1000))
async def test_available_balance_rule_is_deterministic_at_exact_available_boundary(
    required_balance: int,
) -> None:
    rule = AvailableBalanceRule(max_state_age=timedelta(milliseconds=5000))
    context = _context(
        available_balance=Decimal(required_balance),
        observed_at=NOW,
    )

    first = await rule.evaluate(_intent(quantity=required_balance, limit_price="1"), context)
    second = await rule.evaluate(_intent(quantity=required_balance, limit_price="1"), context)

    assert first == second
    assert first.passed is True
    assert first.reason_code == RISK_AVAILABLE_BALANCE_VALID_REASON
    assert first.observed_value == Decimal(required_balance)
    assert first.limit_value == Decimal(required_balance)


@given(
    required_balance=st.integers(min_value=2, max_value=1000),
    shortfall=st.integers(min_value=1, max_value=1000),
)
async def test_available_balance_rule_rejects_any_required_balance_above_available(
    required_balance: int,
    shortfall: int,
) -> None:
    available_balance = max(Decimal("0"), Decimal(required_balance - shortfall))
    if available_balance >= Decimal(required_balance):
        available_balance = Decimal(required_balance - 1)

    result = await AvailableBalanceRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(quantity=required_balance, limit_price="1"),
        _context(
            available_balance=available_balance,
            observed_at=NOW,
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_AVAILABLE_BALANCE_INSUFFICIENT_REASON
    assert result.observed_value == Decimal(required_balance)
    assert result.limit_value == available_balance


@given(
    required_balance=st.integers(min_value=1, max_value=1000),
    reserved_balance=st.integers(min_value=0, max_value=1000),
)
async def test_available_balance_rule_subtracts_reserved_balance_at_exact_boundary(
    required_balance: int,
    reserved_balance: int,
) -> None:
    result = await AvailableBalanceRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(quantity=required_balance, limit_price="1"),
        _context(
            available_balance=Decimal(required_balance + reserved_balance),
            reserved_balance=Decimal(reserved_balance),
            observed_at=NOW,
        ),
    )

    assert result.passed is True
    assert result.reason_code == RISK_AVAILABLE_BALANCE_VALID_REASON
    assert result.observed_value == Decimal(required_balance)
    assert result.limit_value == Decimal(required_balance)


@given(age_ms=st.integers(min_value=5001, max_value=600000))
async def test_available_balance_rule_rejects_any_stale_balance_state(age_ms: int) -> None:
    result = await AvailableBalanceRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(quantity=5, limit_price="1"),
        _context(
            available_balance=Decimal("5"),
            observed_at=NOW - timedelta(milliseconds=age_ms),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_AVAILABLE_BALANCE_STATE_STALE_REASON
    assert result.observed_value == Decimal(age_ms)
    assert result.limit_value == Decimal("5000")


@given(future_ms=st.integers(min_value=1, max_value=600000))
async def test_available_balance_rule_rejects_any_future_balance_state(
    future_ms: int,
) -> None:
    result = await AvailableBalanceRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(quantity=5, limit_price="1"),
        _context(
            available_balance=Decimal("5"),
            observed_at=NOW + timedelta(milliseconds=future_ms),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_AVAILABLE_BALANCE_STATE_FUTURE_REASON
    assert result.observed_value == Decimal(future_ms)
    assert result.limit_value == Decimal("0")


def _context(
    *,
    available_balance: Decimal,
    observed_at: datetime,
    reserved_balance: Decimal = Decimal("0"),
) -> RiskContext:
    return RiskContext(
        evaluated_at=NOW,
        available_balance=RiskAvailableBalanceState(
            available_balance=available_balance,
            reserved_balance=reserved_balance,
            observed_at=observed_at,
        ),
    )


def _intent(*, quantity: int, limit_price: str) -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_risk_available_balance_property",
            "strategy_id": STRATEGY_ID,
            "market_id": MARKET_ID,
            "contract_id": CONTRACT_ID,
            "outcome_id": "out_yes",
            "side": Side.BUY,
            "quantity": str(quantity),
            "limit_price": limit_price,
            "order_type": OrderType.LIMIT,
            "time_in_force": TimeInForce.GTC,
            "post_only": False,
            "reduce_only": False,
            "urgency": "0.75",
            "created_at": NOW,
            "expires_at": NOW + timedelta(seconds=5),
            "signal_ids": (),
            "correlation_id": "corr_risk_available_balance_property",
            "idempotency_key": "idem-risk-available-balance-property",
        }
    )
