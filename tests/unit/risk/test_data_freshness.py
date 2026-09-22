"""Unit tests for the RISK-005 market-data freshness rule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.risk import (
    RISK_MARKET_DATA_FRESH_REASON,
    RISK_MARKET_DATA_FRESH_RULE_ID,
    RISK_MARKET_DATA_FRESH_RULE_VERSION,
    RISK_MARKET_DATA_FUTURE_REASON,
    RISK_MARKET_DATA_MISSING_REASON,
    RISK_MARKET_DATA_NOT_FRESH_REASON,
    RISK_MARKET_DATA_STALE_REASON,
    MarketDataFreshnessRule,
    RiskBooleanState,
    RiskConfigurationError,
    RiskContext,
    RiskInputError,
)
from pmrp.schemas.enums import OrderType, Side, TimeInForce
from pmrp.schemas.identifiers import MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_risk_market_data_fresh")
STRATEGY_ID = StrategyId("strat_risk_market_data_fresh")


async def test_market_data_freshness_rule_passes_fresh_market_data() -> None:
    rule = MarketDataFreshnessRule(max_state_age=timedelta(seconds=5))
    result = await rule.evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            market_data_fresh={
                MARKET_ID: RiskBooleanState(
                    value=True,
                    observed_at=NOW - timedelta(seconds=1),
                )
            },
        ),
    )

    assert rule.rule_id == RISK_MARKET_DATA_FRESH_RULE_ID
    assert rule.version == RISK_MARKET_DATA_FRESH_RULE_VERSION
    assert result.passed is True
    assert result.rule_id == "RISK-005"
    assert result.rule_version == "1.0"
    assert result.reason_code == RISK_MARKET_DATA_FRESH_REASON
    assert result.observed_value == Decimal("1")
    assert result.limit_value == Decimal("1")
    assert result.unit == "fresh_flag"
    assert result.evaluated_at == NOW


async def test_market_data_freshness_rule_rejects_not_fresh_marker() -> None:
    result = await MarketDataFreshnessRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            market_data_fresh={
                MARKET_ID: RiskBooleanState(
                    value=False,
                    observed_at=NOW - timedelta(seconds=1),
                )
            },
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_MARKET_DATA_NOT_FRESH_REASON
    assert result.observed_value == Decimal("0")
    assert result.limit_value == Decimal("1")
    assert result.unit == "fresh_flag"


async def test_market_data_freshness_rule_allows_exact_staleness_boundary() -> None:
    result = await MarketDataFreshnessRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            market_data_fresh={
                MARKET_ID: RiskBooleanState(
                    value=True,
                    observed_at=NOW - timedelta(seconds=5),
                )
            },
        ),
    )

    assert result.passed is True
    assert result.reason_code == RISK_MARKET_DATA_FRESH_REASON


async def test_market_data_freshness_rule_rejects_missing_market_data() -> None:
    result = await MarketDataFreshnessRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(evaluated_at=NOW),
    )

    assert result.passed is False
    assert result.reason_code == RISK_MARKET_DATA_MISSING_REASON
    assert result.observed_value is None
    assert result.limit_value == Decimal("1")
    assert result.unit == "fresh_flag"


async def test_market_data_freshness_rule_rejects_stale_market_data() -> None:
    result = await MarketDataFreshnessRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            market_data_fresh={
                MARKET_ID: RiskBooleanState(
                    value=True,
                    observed_at=NOW - timedelta(seconds=5, milliseconds=1),
                )
            },
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_MARKET_DATA_STALE_REASON
    assert result.observed_value == Decimal("5001")
    assert result.limit_value == Decimal("5000")
    assert result.unit == "milliseconds"


async def test_market_data_freshness_rule_rejects_future_market_data() -> None:
    result = await MarketDataFreshnessRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            market_data_fresh={
                MARKET_ID: RiskBooleanState(
                    value=True,
                    observed_at=NOW + timedelta(milliseconds=1),
                )
            },
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_MARKET_DATA_FUTURE_REASON
    assert result.observed_value == Decimal("1")
    assert result.limit_value == Decimal("0")
    assert result.unit == "milliseconds"


def test_risk_context_market_data_freshness_is_immutable_and_validates_inputs() -> None:
    context = RiskContext(
        evaluated_at=NOW,
        market_data_fresh={
            MARKET_ID: RiskBooleanState(
                value=True,
                observed_at=NOW,
            )
        },
    )

    with pytest.raises(TypeError, match="does not support item assignment"):
        context.market_data_fresh[MARKET_ID] = RiskBooleanState(value=False, observed_at=NOW)
    with pytest.raises(TypeError, match="market_data_fresh"):
        RiskContext(evaluated_at=NOW, market_data_fresh=())  # type: ignore[arg-type]
    with pytest.raises(RiskConfigurationError, match="MarketId"):
        RiskContext(
            evaluated_at=NOW,
            market_data_fresh={
                "mkt_risk_market_data_fresh": RiskBooleanState(value=True, observed_at=NOW)
            },  # type: ignore[dict-item]
        )
    with pytest.raises(RiskConfigurationError, match="RiskBooleanState"):
        RiskContext(
            evaluated_at=NOW,
            market_data_fresh={MARKET_ID: True},  # type: ignore[dict-item]
        )


def test_market_data_freshness_rule_rejects_invalid_configuration() -> None:
    with pytest.raises(RiskConfigurationError, match="max_state_age"):
        MarketDataFreshnessRule(max_state_age=timedelta(0))
    with pytest.raises(TypeError, match="timedelta"):
        MarketDataFreshnessRule(max_state_age=5)  # type: ignore[arg-type]


async def test_market_data_freshness_rule_rejects_invalid_evaluation_inputs() -> None:
    rule = MarketDataFreshnessRule(max_state_age=timedelta(seconds=5))

    with pytest.raises(RiskInputError, match="OrderIntent"):
        await rule.evaluate("intent", RiskContext(evaluated_at=NOW))  # type: ignore[arg-type]
    with pytest.raises(RiskInputError, match="RiskContext"):
        await rule.evaluate(_intent(), "context")  # type: ignore[arg-type]


def _intent() -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_risk_market_data_fresh",
            "strategy_id": STRATEGY_ID,
            "market_id": MARKET_ID,
            "contract_id": "ctr_risk_market_data_fresh",
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
            "correlation_id": "corr_risk_market_data_fresh",
            "idempotency_key": "idem-risk-market-data-fresh",
        }
    )
