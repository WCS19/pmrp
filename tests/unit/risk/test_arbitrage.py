"""Unit tests for the RISK-020 arbitrage-leg risk rule."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.risk import (
    RISK_ARBITRAGE_HEDGE_DEADLINE_MISSING_REASON,
    RISK_ARBITRAGE_HEDGE_TIMEOUT_EXPIRED_REASON,
    RISK_ARBITRAGE_LEG_EXPOSURE_ABOVE_MAX_REASON,
    RISK_ARBITRAGE_LEG_RULE_ID,
    RISK_ARBITRAGE_LEG_RULE_VERSION,
    RISK_ARBITRAGE_LEG_STATE_FUTURE_REASON,
    RISK_ARBITRAGE_LEG_STATE_MISSING_REASON,
    RISK_ARBITRAGE_LEG_STATE_STALE_REASON,
    RISK_ARBITRAGE_LEG_VALID_REASON,
    ArbitrageLegRiskRule,
    RiskArbitrageLegState,
    RiskConfigurationError,
    RiskContext,
    RiskInputError,
)
from pmrp.schemas.enums import OrderType, Side, TimeInForce
from pmrp.schemas.identifiers import ContractId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_risk_arbitrage_leg")
CONTRACT_ID = ContractId("ctr_risk_arbitrage_leg")
STRATEGY_ID = StrategyId("strat_risk_arbitrage_leg")


async def test_arbitrage_leg_risk_rule_passes_below_unhedged_quantity_cap() -> None:
    rule = ArbitrageLegRiskRule(max_state_age=timedelta(seconds=5))
    result = await rule.evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            arbitrage_leg=RiskArbitrageLegState(
                current_unhedged_quantity="4",
                max_unhedged_quantity="5",
                hedge_deadline_at=NOW + timedelta(seconds=10),
                submitted_legs=2,
                accepted_legs=2,
                filled_legs=1,
                observed_at=NOW - timedelta(seconds=1),
            ),
        ),
    )

    assert rule.rule_id == RISK_ARBITRAGE_LEG_RULE_ID
    assert rule.version == RISK_ARBITRAGE_LEG_RULE_VERSION
    assert result.passed is True
    assert result.rule_id == "RISK-020"
    assert result.rule_version == "1.0"
    assert result.reason_code == RISK_ARBITRAGE_LEG_VALID_REASON
    assert result.observed_value == Decimal("4")
    assert result.limit_value == Decimal("5")
    assert result.unit == "quantity"
    assert result.evaluated_at == NOW


async def test_arbitrage_leg_risk_rule_allows_equal_unhedged_quantity_cap() -> None:
    result = await ArbitrageLegRiskRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            arbitrage_leg=RiskArbitrageLegState(
                current_unhedged_quantity="5",
                max_unhedged_quantity="5",
                hedge_deadline_at=NOW + timedelta(seconds=10),
                observed_at=NOW,
            ),
        ),
    )

    assert result.passed is True
    assert result.reason_code == RISK_ARBITRAGE_LEG_VALID_REASON
    assert result.observed_value == Decimal("5")
    assert result.limit_value == Decimal("5")


async def test_arbitrage_leg_risk_rule_allows_zero_unhedged_quantity_without_deadline() -> None:
    result = await ArbitrageLegRiskRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            arbitrage_leg=RiskArbitrageLegState(
                current_unhedged_quantity="0",
                max_unhedged_quantity="0",
                observed_at=NOW,
            ),
        ),
    )

    assert result.passed is True
    assert result.reason_code == RISK_ARBITRAGE_LEG_VALID_REASON
    assert result.observed_value == Decimal("0")
    assert result.limit_value == Decimal("0")


async def test_arbitrage_leg_risk_rule_rejects_missing_state() -> None:
    result = await ArbitrageLegRiskRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(evaluated_at=NOW),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ARBITRAGE_LEG_STATE_MISSING_REASON
    assert result.observed_value is None
    assert result.limit_value is None
    assert result.unit == "quantity"


async def test_arbitrage_leg_risk_rule_rejects_stale_state() -> None:
    result = await ArbitrageLegRiskRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            arbitrage_leg=RiskArbitrageLegState(
                current_unhedged_quantity="4",
                max_unhedged_quantity="5",
                hedge_deadline_at=NOW + timedelta(seconds=10),
                observed_at=NOW - timedelta(seconds=5, milliseconds=1),
            ),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ARBITRAGE_LEG_STATE_STALE_REASON
    assert result.observed_value == Decimal("5001")
    assert result.limit_value == Decimal("5000")
    assert result.unit == "milliseconds"


async def test_arbitrage_leg_risk_rule_rejects_future_state() -> None:
    result = await ArbitrageLegRiskRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            arbitrage_leg=RiskArbitrageLegState(
                current_unhedged_quantity="4",
                max_unhedged_quantity="5",
                hedge_deadline_at=NOW + timedelta(seconds=10),
                observed_at=NOW + timedelta(milliseconds=1),
            ),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ARBITRAGE_LEG_STATE_FUTURE_REASON
    assert result.observed_value == Decimal("1")
    assert result.limit_value == Decimal("0")
    assert result.unit == "milliseconds"


async def test_arbitrage_leg_risk_rule_rejects_unhedged_quantity_above_cap() -> None:
    result = await ArbitrageLegRiskRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            arbitrage_leg=RiskArbitrageLegState(
                current_unhedged_quantity="5.0001",
                max_unhedged_quantity="5",
                hedge_deadline_at=NOW + timedelta(seconds=10),
                observed_at=NOW,
            ),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ARBITRAGE_LEG_EXPOSURE_ABOVE_MAX_REASON
    assert result.observed_value == Decimal("5.0001")
    assert result.limit_value == Decimal("5")
    assert result.unit == "quantity"


async def test_arbitrage_leg_risk_rule_rejects_missing_hedge_deadline() -> None:
    result = await ArbitrageLegRiskRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            arbitrage_leg=RiskArbitrageLegState(
                current_unhedged_quantity="1",
                max_unhedged_quantity="5",
                observed_at=NOW,
            ),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ARBITRAGE_HEDGE_DEADLINE_MISSING_REASON
    assert result.observed_value is None
    assert result.limit_value is None
    assert result.unit == "deadline"


async def test_arbitrage_leg_risk_rule_rejects_expired_hedge_timeout() -> None:
    result = await ArbitrageLegRiskRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            arbitrage_leg=RiskArbitrageLegState(
                current_unhedged_quantity="1",
                max_unhedged_quantity="5",
                hedge_deadline_at=NOW - timedelta(milliseconds=1),
                observed_at=NOW,
            ),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ARBITRAGE_HEDGE_TIMEOUT_EXPIRED_REASON
    assert result.observed_value == Decimal("1")
    assert result.limit_value == Decimal("0")
    assert result.unit == "milliseconds"


def test_risk_context_arbitrage_leg_validates_inputs() -> None:
    context = RiskContext(
        evaluated_at=NOW,
        arbitrage_leg=RiskArbitrageLegState(
            current_unhedged_quantity="1",
            max_unhedged_quantity="5",
            hedge_deadline_at=NOW + timedelta(seconds=10),
            submitted_legs=2,
            accepted_legs=1,
            filled_legs=1,
            observed_at=NOW,
        ),
    )

    assert context.arbitrage_leg_state() == context.arbitrage_leg
    assert context.arbitrage_leg_state().current_unhedged_quantity == Decimal("1")
    with pytest.raises(FrozenInstanceError):
        context.arbitrage_leg = RiskArbitrageLegState(
            current_unhedged_quantity="0",
            max_unhedged_quantity="0",
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="RiskArbitrageLegState"):
        RiskContext(evaluated_at=NOW, arbitrage_leg=True)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="current_unhedged_quantity"):
        RiskArbitrageLegState(
            current_unhedged_quantity=1.0,  # type: ignore[arg-type]
            max_unhedged_quantity="5",
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="current_unhedged_quantity"):
        RiskArbitrageLegState(
            current_unhedged_quantity="-0.01",
            max_unhedged_quantity="5",
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="max_unhedged_quantity"):
        RiskArbitrageLegState(
            current_unhedged_quantity="1",
            max_unhedged_quantity="-0.01",
            observed_at=NOW,
        )
    with pytest.raises(TypeError, match="submitted_legs"):
        RiskArbitrageLegState(
            current_unhedged_quantity="1",
            max_unhedged_quantity="5",
            submitted_legs=1.0,  # type: ignore[arg-type]
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="accepted_legs"):
        RiskArbitrageLegState(
            current_unhedged_quantity="1",
            max_unhedged_quantity="5",
            submitted_legs=1,
            accepted_legs=2,
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="filled_legs"):
        RiskArbitrageLegState(
            current_unhedged_quantity="1",
            max_unhedged_quantity="5",
            submitted_legs=2,
            accepted_legs=1,
            filled_legs=2,
            observed_at=NOW,
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        RiskArbitrageLegState(
            current_unhedged_quantity="1",
            max_unhedged_quantity="5",
            hedge_deadline_at=NOW.replace(tzinfo=None),
            observed_at=NOW,
        )


async def test_arbitrage_leg_risk_rule_rejects_invalid_configuration_and_inputs() -> None:
    rule = ArbitrageLegRiskRule(max_state_age=timedelta(seconds=5))

    with pytest.raises(RiskConfigurationError, match="max_state_age"):
        ArbitrageLegRiskRule(max_state_age=timedelta(0))
    with pytest.raises(TypeError, match="max_state_age"):
        ArbitrageLegRiskRule(max_state_age=5)  # type: ignore[arg-type]
    with pytest.raises(RiskInputError, match="OrderIntent"):
        await rule.evaluate(object(), RiskContext(evaluated_at=NOW))  # type: ignore[arg-type]
    with pytest.raises(RiskInputError, match="RiskContext"):
        await rule.evaluate(_intent(), object())  # type: ignore[arg-type]


def _intent() -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_risk_arbitrage_leg",
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
            "correlation_id": "corr_risk_arbitrage_leg",
            "idempotency_key": "idem-risk-arbitrage-leg",
        }
    )
