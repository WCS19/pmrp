"""Property tests for the RISK-005 market-data freshness rule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.risk import (
    RISK_MARKET_DATA_FRESH_REASON,
    RISK_MARKET_DATA_FUTURE_REASON,
    RISK_MARKET_DATA_NOT_FRESH_REASON,
    RISK_MARKET_DATA_STALE_REASON,
    MarketDataFreshnessRule,
    RiskBooleanState,
    RiskContext,
)
from pmrp.schemas.enums import OrderType, Side, TimeInForce
from pmrp.schemas.identifiers import MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent

pytestmark = pytest.mark.property

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_risk_market_data_fresh_property")
STRATEGY_ID = StrategyId("strat_risk_market_data_fresh_property")


@given(fresh=st.booleans(), age_ms=st.integers(min_value=0, max_value=5000))
async def test_market_data_freshness_rule_is_deterministic_with_fresh_state(
    fresh: bool,
    age_ms: int,
) -> None:
    rule = MarketDataFreshnessRule(max_state_age=timedelta(milliseconds=5000))
    context = RiskContext(
        evaluated_at=NOW,
        market_data_fresh={
            MARKET_ID: RiskBooleanState(
                value=fresh,
                observed_at=NOW - timedelta(milliseconds=age_ms),
            )
        },
    )

    first = await rule.evaluate(_intent(), context)
    second = await rule.evaluate(_intent(), context)

    assert first == second
    assert first.passed is fresh
    assert first.reason_code == (
        RISK_MARKET_DATA_FRESH_REASON if fresh else RISK_MARKET_DATA_NOT_FRESH_REASON
    )
    assert first.observed_value == (Decimal("1") if fresh else Decimal("0"))
    assert first.limit_value == Decimal("1")


@given(age_ms=st.integers(min_value=5001, max_value=600000))
async def test_market_data_freshness_rule_rejects_any_stale_state(age_ms: int) -> None:
    result = await MarketDataFreshnessRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            market_data_fresh={
                MARKET_ID: RiskBooleanState(
                    value=True,
                    observed_at=NOW - timedelta(milliseconds=age_ms),
                )
            },
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_MARKET_DATA_STALE_REASON
    assert result.observed_value == Decimal(age_ms)
    assert result.limit_value == Decimal("5000")


@given(future_ms=st.integers(min_value=1, max_value=600000))
async def test_market_data_freshness_rule_rejects_any_future_state(future_ms: int) -> None:
    result = await MarketDataFreshnessRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            market_data_fresh={
                MARKET_ID: RiskBooleanState(
                    value=True,
                    observed_at=NOW + timedelta(milliseconds=future_ms),
                )
            },
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_MARKET_DATA_FUTURE_REASON
    assert result.observed_value == Decimal(future_ms)
    assert result.limit_value == Decimal("0")


def _intent() -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_risk_market_data_fresh_property",
            "strategy_id": STRATEGY_ID,
            "market_id": MARKET_ID,
            "contract_id": "ctr_risk_market_data_fresh_property",
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
            "correlation_id": "corr_risk_market_data_fresh_property",
            "idempotency_key": "idem-risk-market-data-fresh-property",
        }
    )
