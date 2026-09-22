"""Property tests for the RISK-014 daily-loss limit rule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.risk import (
    RISK_DAILY_LOSS_ABOVE_MAX_REASON,
    RISK_DAILY_LOSS_STATE_FUTURE_REASON,
    RISK_DAILY_LOSS_STATE_STALE_REASON,
    RISK_DAILY_LOSS_VALID_REASON,
    DailyLossLimitRule,
    RiskContext,
    RiskDailyLossState,
)
from pmrp.schemas.enums import OrderType, Side, TimeInForce
from pmrp.schemas.identifiers import ContractId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent

pytestmark = pytest.mark.property

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_risk_daily_loss_property")
CONTRACT_ID = ContractId("ctr_risk_daily_loss_property")
STRATEGY_ID = StrategyId("strat_risk_daily_loss_property")


@given(
    loss_cents=st.integers(min_value=1, max_value=100000),
    unrealized_cents=st.integers(min_value=-100000, max_value=100000),
)
async def test_daily_loss_limit_rule_is_deterministic_at_exact_cap(
    loss_cents: int,
    unrealized_cents: int,
) -> None:
    loss = Decimal(loss_cents) / Decimal("100")
    unrealized = Decimal(unrealized_cents) / Decimal("100")
    realized = -loss - unrealized
    rule = DailyLossLimitRule(max_state_age=timedelta(milliseconds=5000))
    context = _context(
        daily_realized_pnl=realized,
        daily_unrealized_pnl=unrealized,
        max_daily_loss=loss,
        observed_at=NOW,
    )

    first = await rule.evaluate(_intent(), context)
    second = await rule.evaluate(_intent(), context)

    assert first == second
    assert first.passed is True
    assert first.reason_code == RISK_DAILY_LOSS_VALID_REASON
    assert first.observed_value == loss
    assert first.limit_value == loss


@given(
    max_loss_cents=st.integers(min_value=1, max_value=100000),
    excess_cents=st.integers(min_value=1, max_value=100000),
    unrealized_cents=st.integers(min_value=-100000, max_value=100000),
)
async def test_daily_loss_limit_rule_rejects_any_loss_above_cap(
    max_loss_cents: int,
    excess_cents: int,
    unrealized_cents: int,
) -> None:
    max_loss = Decimal(max_loss_cents) / Decimal("100")
    excess = Decimal(excess_cents) / Decimal("100")
    current_loss = max_loss + excess
    unrealized = Decimal(unrealized_cents) / Decimal("100")
    realized = -current_loss - unrealized

    result = await DailyLossLimitRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(),
        _context(
            daily_realized_pnl=realized,
            daily_unrealized_pnl=unrealized,
            max_daily_loss=max_loss,
            observed_at=NOW,
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_DAILY_LOSS_ABOVE_MAX_REASON
    assert result.observed_value == current_loss
    assert result.limit_value == max_loss


@given(
    realized_cents=st.integers(min_value=0, max_value=100000),
    unrealized_cents=st.integers(min_value=0, max_value=100000),
    max_loss_cents=st.integers(min_value=1, max_value=100000),
)
async def test_daily_loss_limit_rule_treats_nonnegative_pnl_as_zero_loss(
    realized_cents: int,
    unrealized_cents: int,
    max_loss_cents: int,
) -> None:
    result = await DailyLossLimitRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(),
        _context(
            daily_realized_pnl=Decimal(realized_cents) / Decimal("100"),
            daily_unrealized_pnl=Decimal(unrealized_cents) / Decimal("100"),
            max_daily_loss=Decimal(max_loss_cents) / Decimal("100"),
            observed_at=NOW,
        ),
    )

    assert result.passed is True
    assert result.reason_code == RISK_DAILY_LOSS_VALID_REASON
    assert result.observed_value == Decimal("0")


@given(age_ms=st.integers(min_value=5001, max_value=600000))
async def test_daily_loss_limit_rule_rejects_any_stale_daily_loss_state(age_ms: int) -> None:
    result = await DailyLossLimitRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(),
        _context(
            daily_realized_pnl=Decimal("-75"),
            daily_unrealized_pnl=Decimal("10"),
            max_daily_loss=Decimal("100"),
            observed_at=NOW - timedelta(milliseconds=age_ms),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_DAILY_LOSS_STATE_STALE_REASON
    assert result.observed_value == Decimal(age_ms)
    assert result.limit_value == Decimal("5000")


@given(future_ms=st.integers(min_value=1, max_value=600000))
async def test_daily_loss_limit_rule_rejects_any_future_daily_loss_state(
    future_ms: int,
) -> None:
    result = await DailyLossLimitRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(),
        _context(
            daily_realized_pnl=Decimal("-75"),
            daily_unrealized_pnl=Decimal("10"),
            max_daily_loss=Decimal("100"),
            observed_at=NOW + timedelta(milliseconds=future_ms),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_DAILY_LOSS_STATE_FUTURE_REASON
    assert result.observed_value == Decimal(future_ms)
    assert result.limit_value == Decimal("0")


def _context(
    *,
    daily_realized_pnl: Decimal,
    daily_unrealized_pnl: Decimal,
    max_daily_loss: Decimal,
    observed_at: datetime,
) -> RiskContext:
    return RiskContext(
        evaluated_at=NOW,
        daily_loss=RiskDailyLossState(
            daily_realized_pnl=daily_realized_pnl,
            daily_unrealized_pnl=daily_unrealized_pnl,
            max_daily_loss=max_daily_loss,
            observed_at=observed_at,
        ),
    )


def _intent() -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_risk_daily_loss_property",
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
            "correlation_id": "corr_risk_daily_loss_property",
            "idempotency_key": "idem-risk-daily-loss-property",
        }
    )
