"""Unit tests for the RISK-001 strategy-enabled rule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.risk import (
    RISK_STRATEGY_DISABLED_REASON,
    RISK_STRATEGY_ENABLED_REASON,
    RISK_STRATEGY_ENABLED_RULE_ID,
    RISK_STRATEGY_ENABLED_RULE_VERSION,
    RISK_STRATEGY_STATE_FUTURE_REASON,
    RISK_STRATEGY_STATE_MISSING_REASON,
    RISK_STRATEGY_STATE_STALE_REASON,
    RiskBooleanState,
    RiskConfigurationError,
    RiskContext,
    RiskInputError,
    StrategyEnabledRule,
)
from pmrp.schemas.enums import OrderType, Side, TimeInForce
from pmrp.schemas.identifiers import StrategyId
from pmrp.schemas.orders import OrderIntent

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
STRATEGY_ID = StrategyId("strat_risk_strategy_enabled")


async def test_strategy_enabled_rule_passes_enabled_strategy() -> None:
    rule = StrategyEnabledRule(max_state_age=timedelta(seconds=5))
    result = await rule.evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            strategy_enabled={
                STRATEGY_ID: RiskBooleanState(
                    value=True,
                    observed_at=NOW - timedelta(seconds=1),
                )
            },
        ),
    )

    assert rule.rule_id == RISK_STRATEGY_ENABLED_RULE_ID
    assert rule.version == RISK_STRATEGY_ENABLED_RULE_VERSION
    assert result.passed is True
    assert result.rule_id == "RISK-001"
    assert result.rule_version == "1.0"
    assert result.reason_code == RISK_STRATEGY_ENABLED_REASON
    assert result.observed_value == Decimal("1")
    assert result.limit_value == Decimal("1")
    assert result.unit == "enabled_flag"
    assert result.evaluated_at == NOW


async def test_strategy_enabled_rule_rejects_disabled_strategy() -> None:
    result = await StrategyEnabledRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            strategy_enabled={
                STRATEGY_ID: RiskBooleanState(
                    value=False,
                    observed_at=NOW - timedelta(seconds=1),
                )
            },
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_STRATEGY_DISABLED_REASON
    assert result.observed_value == Decimal("0")
    assert result.limit_value == Decimal("1")
    assert result.unit == "enabled_flag"


async def test_strategy_enabled_rule_allows_exact_staleness_boundary() -> None:
    result = await StrategyEnabledRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            strategy_enabled={
                STRATEGY_ID: RiskBooleanState(
                    value=True,
                    observed_at=NOW - timedelta(seconds=5),
                )
            },
        ),
    )

    assert result.passed is True
    assert result.reason_code == RISK_STRATEGY_ENABLED_REASON


async def test_strategy_enabled_rule_rejects_missing_strategy_state() -> None:
    result = await StrategyEnabledRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(evaluated_at=NOW),
    )

    assert result.passed is False
    assert result.reason_code == RISK_STRATEGY_STATE_MISSING_REASON
    assert result.observed_value is None
    assert result.limit_value == Decimal("1")
    assert result.unit == "enabled_flag"


async def test_strategy_enabled_rule_rejects_stale_strategy_state() -> None:
    result = await StrategyEnabledRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            strategy_enabled={
                STRATEGY_ID: RiskBooleanState(
                    value=True,
                    observed_at=NOW - timedelta(seconds=5, milliseconds=1),
                )
            },
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_STRATEGY_STATE_STALE_REASON
    assert result.observed_value == Decimal("5001")
    assert result.limit_value == Decimal("5000")
    assert result.unit == "milliseconds"


async def test_strategy_enabled_rule_rejects_future_strategy_state() -> None:
    result = await StrategyEnabledRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            strategy_enabled={
                STRATEGY_ID: RiskBooleanState(
                    value=True,
                    observed_at=NOW + timedelta(milliseconds=1),
                )
            },
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_STRATEGY_STATE_FUTURE_REASON
    assert result.observed_value == Decimal("1")
    assert result.limit_value == Decimal("0")
    assert result.unit == "milliseconds"


def test_risk_context_is_immutable_and_validates_utc_inputs() -> None:
    context = RiskContext(
        evaluated_at=NOW,
        strategy_enabled={
            STRATEGY_ID: RiskBooleanState(
                value=True,
                observed_at=NOW,
            )
        },
    )

    with pytest.raises(TypeError, match="does not support item assignment"):
        context.strategy_enabled[STRATEGY_ID] = RiskBooleanState(value=False, observed_at=NOW)
    with pytest.raises(ValueError, match="timezone-aware"):
        RiskContext(evaluated_at=datetime.fromisoformat("2026-09-22T12:00:00"))
    with pytest.raises(ValueError, match="timezone-aware"):
        RiskBooleanState(value=True, observed_at=datetime.fromisoformat("2026-09-22T12:00:00"))


def test_strategy_enabled_rule_rejects_invalid_configuration_and_inputs() -> None:
    with pytest.raises(RiskConfigurationError, match="max_state_age"):
        StrategyEnabledRule(max_state_age=timedelta(0))
    with pytest.raises(TypeError, match="timedelta"):
        StrategyEnabledRule(max_state_age=5)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="bool"):
        RiskBooleanState(value=1, observed_at=NOW)  # type: ignore[arg-type]
    with pytest.raises(RiskConfigurationError, match="StrategyId"):
        RiskContext(
            evaluated_at=NOW,
            strategy_enabled={
                "strat_risk_strategy_enabled": RiskBooleanState(value=True, observed_at=NOW)
            },  # type: ignore[dict-item]
        )


async def test_strategy_enabled_rule_rejects_invalid_evaluation_inputs() -> None:
    rule = StrategyEnabledRule(max_state_age=timedelta(seconds=5))

    with pytest.raises(RiskInputError, match="OrderIntent"):
        await rule.evaluate("intent", RiskContext(evaluated_at=NOW))  # type: ignore[arg-type]
    with pytest.raises(RiskInputError, match="RiskContext"):
        await rule.evaluate(_intent(), "context")  # type: ignore[arg-type]


def _intent() -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_risk_strategy_enabled",
            "strategy_id": STRATEGY_ID,
            "market_id": "mkt_risk_strategy_enabled",
            "contract_id": "ctr_risk_strategy_enabled",
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
            "correlation_id": "corr_risk_strategy_enabled",
            "idempotency_key": "idem-risk-strategy-enabled",
        }
    )
