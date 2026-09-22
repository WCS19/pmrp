"""Unit tests for the RISK-008 order-notional limit rule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.risk import (
    RISK_ORDER_NOTIONAL_ABOVE_MAX_REASON,
    RISK_ORDER_NOTIONAL_LIMIT_FUTURE_REASON,
    RISK_ORDER_NOTIONAL_LIMIT_MISSING_REASON,
    RISK_ORDER_NOTIONAL_LIMIT_RULE_ID,
    RISK_ORDER_NOTIONAL_LIMIT_RULE_VERSION,
    RISK_ORDER_NOTIONAL_LIMIT_STALE_REASON,
    RISK_ORDER_NOTIONAL_PRICE_MISSING_REASON,
    RISK_ORDER_NOTIONAL_VALID_REASON,
    OrderNotionalLimitRule,
    RiskConfigurationError,
    RiskContext,
    RiskInputError,
    RiskNotionalLimitState,
)
from pmrp.schemas.enums import OrderType, Side, TimeInForce
from pmrp.schemas.identifiers import ContractId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_risk_order_notional")
CONTRACT_ID = ContractId("ctr_risk_order_notional")
STRATEGY_ID = StrategyId("strat_risk_order_notional")


async def test_order_notional_limit_rule_passes_notional_under_cap() -> None:
    rule = OrderNotionalLimitRule(max_state_age=timedelta(seconds=5))
    result = await rule.evaluate(
        _intent(quantity="10", limit_price="0.43"),
        RiskContext(
            evaluated_at=NOW,
            notional_limits={
                CONTRACT_ID: RiskNotionalLimitState(
                    max_notional=Decimal("5"),
                    observed_at=NOW - timedelta(seconds=1),
                )
            },
        ),
    )

    assert rule.rule_id == RISK_ORDER_NOTIONAL_LIMIT_RULE_ID
    assert rule.version == RISK_ORDER_NOTIONAL_LIMIT_RULE_VERSION
    assert result.passed is True
    assert result.rule_id == "RISK-008"
    assert result.rule_version == "1.0"
    assert result.reason_code == RISK_ORDER_NOTIONAL_VALID_REASON
    assert result.observed_value == Decimal("4.30")
    assert result.limit_value == Decimal("5")
    assert result.unit == "notional"
    assert result.evaluated_at == NOW


async def test_order_notional_limit_rule_allows_exact_cap_boundary() -> None:
    result = await OrderNotionalLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price="0.50"),
        RiskContext(
            evaluated_at=NOW,
            notional_limits={
                CONTRACT_ID: RiskNotionalLimitState(
                    max_notional=Decimal("5"),
                    observed_at=NOW,
                )
            },
        ),
    )

    assert result.passed is True
    assert result.reason_code == RISK_ORDER_NOTIONAL_VALID_REASON
    assert result.observed_value == Decimal("5.00")
    assert result.limit_value == Decimal("5")


async def test_order_notional_limit_rule_rejects_missing_limit_price() -> None:
    result = await OrderNotionalLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price=None, order_type=OrderType.MARKET),
        RiskContext(evaluated_at=NOW),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ORDER_NOTIONAL_PRICE_MISSING_REASON
    assert result.observed_value is None
    assert result.limit_value is None
    assert result.unit == "notional"


async def test_order_notional_limit_rule_rejects_missing_notional_limit() -> None:
    result = await OrderNotionalLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price="0.43"),
        RiskContext(evaluated_at=NOW),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ORDER_NOTIONAL_LIMIT_MISSING_REASON
    assert result.observed_value == Decimal("4.30")
    assert result.limit_value is None
    assert result.unit == "notional"


async def test_order_notional_limit_rule_rejects_stale_notional_limit() -> None:
    result = await OrderNotionalLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price="0.43"),
        RiskContext(
            evaluated_at=NOW,
            notional_limits={
                CONTRACT_ID: RiskNotionalLimitState(
                    max_notional=Decimal("5"),
                    observed_at=NOW - timedelta(seconds=5, milliseconds=1),
                )
            },
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ORDER_NOTIONAL_LIMIT_STALE_REASON
    assert result.observed_value == Decimal("5001")
    assert result.limit_value == Decimal("5000")
    assert result.unit == "milliseconds"


async def test_order_notional_limit_rule_rejects_future_notional_limit() -> None:
    result = await OrderNotionalLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price="0.43"),
        RiskContext(
            evaluated_at=NOW,
            notional_limits={
                CONTRACT_ID: RiskNotionalLimitState(
                    max_notional=Decimal("5"),
                    observed_at=NOW + timedelta(milliseconds=1),
                )
            },
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ORDER_NOTIONAL_LIMIT_FUTURE_REASON
    assert result.observed_value == Decimal("1")
    assert result.limit_value == Decimal("0")
    assert result.unit == "milliseconds"


async def test_order_notional_limit_rule_rejects_notional_above_cap() -> None:
    result = await OrderNotionalLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price="0.51"),
        RiskContext(
            evaluated_at=NOW,
            notional_limits={
                CONTRACT_ID: RiskNotionalLimitState(
                    max_notional=Decimal("5"),
                    observed_at=NOW,
                )
            },
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ORDER_NOTIONAL_ABOVE_MAX_REASON
    assert result.observed_value == Decimal("5.10")
    assert result.limit_value == Decimal("5")
    assert result.unit == "notional"


def test_risk_context_notional_limits_are_immutable_and_validate_inputs() -> None:
    context = RiskContext(
        evaluated_at=NOW,
        notional_limits={
            CONTRACT_ID: RiskNotionalLimitState(
                max_notional=Decimal("5"),
                observed_at=NOW,
            )
        },
    )

    with pytest.raises(TypeError, match="does not support item assignment"):
        context.notional_limits[CONTRACT_ID] = RiskNotionalLimitState(
            max_notional=Decimal("5"),
            observed_at=NOW,
        )
    with pytest.raises(TypeError, match="notional_limits"):
        RiskContext(evaluated_at=NOW, notional_limits=())  # type: ignore[arg-type]
    with pytest.raises(RiskConfigurationError, match="ContractId"):
        RiskContext(
            evaluated_at=NOW,
            notional_limits={
                "ctr_risk_order_notional": RiskNotionalLimitState(
                    max_notional=Decimal("5"),
                    observed_at=NOW,
                )
            },  # type: ignore[dict-item]
        )
    with pytest.raises(RiskConfigurationError, match="RiskNotionalLimitState"):
        RiskContext(
            evaluated_at=NOW,
            notional_limits={CONTRACT_ID: True},  # type: ignore[dict-item]
        )
    with pytest.raises(TypeError, match="float"):
        RiskNotionalLimitState(
            max_notional=5.0,  # type: ignore[arg-type]
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="max_notional"):
        RiskNotionalLimitState(
            max_notional=Decimal("0"),
            observed_at=NOW,
        )


def test_order_notional_limit_rule_rejects_invalid_configuration() -> None:
    with pytest.raises(RiskConfigurationError, match="max_state_age"):
        OrderNotionalLimitRule(max_state_age=timedelta(0))
    with pytest.raises(TypeError, match="timedelta"):
        OrderNotionalLimitRule(max_state_age=5)  # type: ignore[arg-type]


async def test_order_notional_limit_rule_rejects_invalid_evaluation_inputs() -> None:
    rule = OrderNotionalLimitRule(max_state_age=timedelta(seconds=5))

    with pytest.raises(RiskInputError, match="OrderIntent"):
        await rule.evaluate("intent", RiskContext(evaluated_at=NOW))  # type: ignore[arg-type]
    with pytest.raises(RiskInputError, match="RiskContext"):
        await rule.evaluate(_intent(quantity="10", limit_price="0.43"), "context")  # type: ignore[arg-type]


def _intent(
    *,
    quantity: str,
    limit_price: str | None,
    order_type: OrderType = OrderType.LIMIT,
) -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_risk_order_notional",
            "strategy_id": STRATEGY_ID,
            "market_id": MARKET_ID,
            "contract_id": CONTRACT_ID,
            "outcome_id": "out_yes",
            "side": Side.BUY,
            "quantity": quantity,
            "limit_price": limit_price,
            "order_type": order_type,
            "time_in_force": TimeInForce.GTC,
            "post_only": False,
            "reduce_only": False,
            "urgency": "0.75",
            "created_at": NOW,
            "expires_at": NOW + timedelta(seconds=5),
            "signal_ids": (),
            "correlation_id": "corr_risk_order_notional",
            "idempotency_key": "idem-risk-order-notional",
        }
    )
