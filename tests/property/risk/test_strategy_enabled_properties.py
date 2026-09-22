"""Property tests for the RISK-001 strategy-enabled rule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.risk import (
    RISK_STRATEGY_DISABLED_REASON,
    RISK_STRATEGY_ENABLED_REASON,
    RISK_STRATEGY_STATE_FUTURE_REASON,
    RISK_STRATEGY_STATE_STALE_REASON,
    RiskBooleanState,
    RiskContext,
    StrategyEnabledRule,
)
from pmrp.schemas.enums import OrderType, Side, TimeInForce
from pmrp.schemas.identifiers import StrategyId
from pmrp.schemas.orders import OrderIntent

pytestmark = pytest.mark.property

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
STRATEGY_ID = StrategyId("strat_risk_strategy_enabled_property")


@given(enabled=st.booleans(), age_ms=st.integers(min_value=0, max_value=5000))
async def test_strategy_enabled_rule_is_deterministic_with_fresh_state(
    enabled: bool,
    age_ms: int,
) -> None:
    rule = StrategyEnabledRule(max_state_age=timedelta(milliseconds=5000))
    context = RiskContext(
        evaluated_at=NOW,
        strategy_enabled={
            STRATEGY_ID: RiskBooleanState(
                value=enabled,
                observed_at=NOW - timedelta(milliseconds=age_ms),
            )
        },
    )

    first = await rule.evaluate(_intent(), context)
    second = await rule.evaluate(_intent(), context)

    assert first == second
    assert first.passed is enabled
    assert first.reason_code == (
        RISK_STRATEGY_ENABLED_REASON if enabled else RISK_STRATEGY_DISABLED_REASON
    )
    assert first.observed_value == (Decimal("1") if enabled else Decimal("0"))
    assert first.limit_value == Decimal("1")


@given(age_ms=st.integers(min_value=5001, max_value=600000))
async def test_strategy_enabled_rule_rejects_any_stale_state(age_ms: int) -> None:
    result = await StrategyEnabledRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            strategy_enabled={
                STRATEGY_ID: RiskBooleanState(
                    value=True,
                    observed_at=NOW - timedelta(milliseconds=age_ms),
                )
            },
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_STRATEGY_STATE_STALE_REASON
    assert result.observed_value == Decimal(age_ms)
    assert result.limit_value == Decimal("5000")


@given(future_ms=st.integers(min_value=1, max_value=600000))
async def test_strategy_enabled_rule_rejects_any_future_state(future_ms: int) -> None:
    result = await StrategyEnabledRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            strategy_enabled={
                STRATEGY_ID: RiskBooleanState(
                    value=True,
                    observed_at=NOW + timedelta(milliseconds=future_ms),
                )
            },
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_STRATEGY_STATE_FUTURE_REASON
    assert result.observed_value == Decimal(future_ms)
    assert result.limit_value == Decimal("0")


def _intent() -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_risk_strategy_enabled_property",
            "strategy_id": STRATEGY_ID,
            "market_id": "mkt_risk_strategy_enabled_property",
            "contract_id": "ctr_risk_strategy_enabled_property",
            "outcome_id": "out_yes",
            "side": Side.BUY,
            "quantity": "10",
            "limit_price": "0.43",
            "order_type": OrderType.LIMIT,
            "time_in_force": TimeInForce.GTC,
            "post_only": False,
            "reduce_only": False,
            "urgency": "0.75",
            "created_at": NOW,
            "expires_at": NOW + timedelta(seconds=5),
            "signal_ids": (),
            "correlation_id": "corr_risk_strategy_enabled_property",
            "idempotency_key": "idem-risk-strategy-enabled-property",
        }
    )
