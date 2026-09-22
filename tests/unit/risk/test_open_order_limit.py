"""Unit tests for the RISK-015 open-order limit rule."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.risk import (
    RISK_OPEN_ORDER_LIMIT_ABOVE_MAX_REASON,
    RISK_OPEN_ORDER_LIMIT_RULE_ID,
    RISK_OPEN_ORDER_LIMIT_RULE_VERSION,
    RISK_OPEN_ORDER_LIMIT_STATE_FUTURE_REASON,
    RISK_OPEN_ORDER_LIMIT_STATE_MISSING_REASON,
    RISK_OPEN_ORDER_LIMIT_STATE_STALE_REASON,
    RISK_OPEN_ORDER_LIMIT_VALID_REASON,
    OpenOrderLimitRule,
    RiskConfigurationError,
    RiskContext,
    RiskInputError,
    RiskOpenOrderLimitState,
)
from pmrp.schemas.enums import OrderType, Side, TimeInForce
from pmrp.schemas.identifiers import ContractId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_risk_open_order_limit")
CONTRACT_ID = ContractId("ctr_risk_open_order_limit")
STRATEGY_ID = StrategyId("strat_risk_open_order_limit")


async def test_open_order_limit_rule_passes_projected_count_under_cap() -> None:
    rule = OpenOrderLimitRule(max_state_age=timedelta(seconds=5))
    result = await rule.evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            open_order_limit=RiskOpenOrderLimitState(
                current_open_orders=8,
                max_open_orders=10,
                observed_at=NOW - timedelta(seconds=1),
            ),
        ),
    )

    assert rule.rule_id == RISK_OPEN_ORDER_LIMIT_RULE_ID
    assert rule.version == RISK_OPEN_ORDER_LIMIT_RULE_VERSION
    assert result.passed is True
    assert result.rule_id == "RISK-015"
    assert result.rule_version == "1.0"
    assert result.reason_code == RISK_OPEN_ORDER_LIMIT_VALID_REASON
    assert result.observed_value == Decimal("9")
    assert result.limit_value == Decimal("10")
    assert result.unit == "orders"
    assert result.evaluated_at == NOW


async def test_open_order_limit_rule_allows_exact_cap_boundary() -> None:
    result = await OpenOrderLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            open_order_limit=RiskOpenOrderLimitState(
                current_open_orders=9,
                max_open_orders=10,
                observed_at=NOW,
            ),
        ),
    )

    assert result.passed is True
    assert result.reason_code == RISK_OPEN_ORDER_LIMIT_VALID_REASON
    assert result.observed_value == Decimal("10")
    assert result.limit_value == Decimal("10")


async def test_open_order_limit_rule_includes_pending_cancels_and_reservations() -> None:
    result = await OpenOrderLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            open_order_limit=RiskOpenOrderLimitState(
                current_open_orders=5,
                pending_cancel_orders=2,
                reserved_open_orders=2,
                max_open_orders=10,
                observed_at=NOW,
            ),
        ),
    )

    assert result.passed is True
    assert result.reason_code == RISK_OPEN_ORDER_LIMIT_VALID_REASON
    assert result.observed_value == Decimal("10")
    assert result.limit_value == Decimal("10")


async def test_open_order_limit_rule_rejects_missing_open_order_state() -> None:
    result = await OpenOrderLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(evaluated_at=NOW),
    )

    assert result.passed is False
    assert result.reason_code == RISK_OPEN_ORDER_LIMIT_STATE_MISSING_REASON
    assert result.observed_value is None
    assert result.limit_value is None
    assert result.unit == "orders"


async def test_open_order_limit_rule_rejects_stale_open_order_state() -> None:
    result = await OpenOrderLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            open_order_limit=RiskOpenOrderLimitState(
                current_open_orders=8,
                max_open_orders=10,
                observed_at=NOW - timedelta(seconds=5, milliseconds=1),
            ),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_OPEN_ORDER_LIMIT_STATE_STALE_REASON
    assert result.observed_value == Decimal("5001")
    assert result.limit_value == Decimal("5000")
    assert result.unit == "milliseconds"


async def test_open_order_limit_rule_rejects_future_open_order_state() -> None:
    result = await OpenOrderLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            open_order_limit=RiskOpenOrderLimitState(
                current_open_orders=8,
                max_open_orders=10,
                observed_at=NOW + timedelta(milliseconds=1),
            ),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_OPEN_ORDER_LIMIT_STATE_FUTURE_REASON
    assert result.observed_value == Decimal("1")
    assert result.limit_value == Decimal("0")
    assert result.unit == "milliseconds"


async def test_open_order_limit_rule_rejects_count_above_cap() -> None:
    result = await OpenOrderLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            open_order_limit=RiskOpenOrderLimitState(
                current_open_orders=10,
                max_open_orders=10,
                observed_at=NOW,
            ),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_OPEN_ORDER_LIMIT_ABOVE_MAX_REASON
    assert result.observed_value == Decimal("11")
    assert result.limit_value == Decimal("10")
    assert result.unit == "orders"


def test_risk_context_open_order_limit_validates_inputs() -> None:
    context = RiskContext(
        evaluated_at=NOW,
        open_order_limit=RiskOpenOrderLimitState(
            current_open_orders=8,
            max_open_orders=10,
            observed_at=NOW,
        ),
    )

    assert context.open_order_limit_state() == context.open_order_limit
    assert context.open_order_limit_state().effective_open_order_count == 8
    with pytest.raises(FrozenInstanceError):
        context.open_order_limit = RiskOpenOrderLimitState(
            current_open_orders=8,
            max_open_orders=10,
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="RiskOpenOrderLimitState"):
        RiskContext(evaluated_at=NOW, open_order_limit=True)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="current_open_orders"):
        RiskOpenOrderLimitState(
            current_open_orders=True,  # type: ignore[arg-type]
            max_open_orders=10,
            observed_at=NOW,
        )
    with pytest.raises(TypeError, match="pending_cancel_orders"):
        RiskOpenOrderLimitState(
            current_open_orders=8,
            pending_cancel_orders=1.0,  # type: ignore[arg-type]
            max_open_orders=10,
            observed_at=NOW,
        )
    with pytest.raises(TypeError, match="reserved_open_orders"):
        RiskOpenOrderLimitState(
            current_open_orders=8,
            reserved_open_orders=1.0,  # type: ignore[arg-type]
            max_open_orders=10,
            observed_at=NOW,
        )
    with pytest.raises(TypeError, match="max_open_orders"):
        RiskOpenOrderLimitState(
            current_open_orders=8,
            max_open_orders=10.0,  # type: ignore[arg-type]
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="current_open_orders"):
        RiskOpenOrderLimitState(
            current_open_orders=-1,
            max_open_orders=10,
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="pending_cancel_orders"):
        RiskOpenOrderLimitState(
            current_open_orders=8,
            pending_cancel_orders=-1,
            max_open_orders=10,
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="reserved_open_orders"):
        RiskOpenOrderLimitState(
            current_open_orders=8,
            reserved_open_orders=-1,
            max_open_orders=10,
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="max_open_orders"):
        RiskOpenOrderLimitState(
            current_open_orders=8,
            max_open_orders=0,
            observed_at=NOW,
        )


async def test_open_order_limit_rule_rejects_invalid_configuration_and_inputs() -> None:
    rule = OpenOrderLimitRule(max_state_age=timedelta(seconds=5))

    with pytest.raises(RiskConfigurationError, match="max_state_age"):
        OpenOrderLimitRule(max_state_age=timedelta(0))
    with pytest.raises(TypeError, match="max_state_age"):
        OpenOrderLimitRule(max_state_age=5)  # type: ignore[arg-type]
    with pytest.raises(RiskInputError, match="OrderIntent"):
        await rule.evaluate(object(), RiskContext(evaluated_at=NOW))  # type: ignore[arg-type]
    with pytest.raises(RiskInputError, match="RiskContext"):
        await rule.evaluate(_intent(), object())  # type: ignore[arg-type]


def _intent() -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_risk_open_order_limit",
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
            "correlation_id": "corr_risk_open_order_limit",
            "idempotency_key": "idem-risk-open-order-limit",
        }
    )
