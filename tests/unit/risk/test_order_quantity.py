"""Unit tests for the RISK-007 order-quantity limit rule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.risk import (
    RISK_ORDER_QUANTITY_ABOVE_MAX_REASON,
    RISK_ORDER_QUANTITY_BELOW_MIN_REASON,
    RISK_ORDER_QUANTITY_LIMIT_RULE_ID,
    RISK_ORDER_QUANTITY_LIMIT_RULE_VERSION,
    RISK_ORDER_QUANTITY_LIMITS_FUTURE_REASON,
    RISK_ORDER_QUANTITY_LIMITS_MISSING_REASON,
    RISK_ORDER_QUANTITY_LIMITS_STALE_REASON,
    RISK_ORDER_QUANTITY_OFF_INCREMENT_REASON,
    RISK_ORDER_QUANTITY_VALID_REASON,
    OrderQuantityLimitRule,
    RiskConfigurationError,
    RiskContext,
    RiskInputError,
    RiskQuantityLimitsState,
)
from pmrp.schemas.enums import OrderType, Side, TimeInForce
from pmrp.schemas.identifiers import ContractId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_risk_order_quantity")
CONTRACT_ID = ContractId("ctr_risk_order_quantity")
STRATEGY_ID = StrategyId("strat_risk_order_quantity")


async def test_order_quantity_limit_rule_passes_quantity_within_limits_and_increment() -> None:
    rule = OrderQuantityLimitRule(max_state_age=timedelta(seconds=5))
    result = await rule.evaluate(
        _intent(quantity="10"),
        RiskContext(
            evaluated_at=NOW,
            quantity_limits={
                CONTRACT_ID: RiskQuantityLimitsState(
                    min_quantity=Decimal("1"),
                    max_quantity=Decimal("100"),
                    quantity_increment=Decimal("1"),
                    observed_at=NOW - timedelta(seconds=1),
                )
            },
        ),
    )

    assert rule.rule_id == RISK_ORDER_QUANTITY_LIMIT_RULE_ID
    assert rule.version == RISK_ORDER_QUANTITY_LIMIT_RULE_VERSION
    assert result.passed is True
    assert result.rule_id == "RISK-007"
    assert result.rule_version == "1.0"
    assert result.reason_code == RISK_ORDER_QUANTITY_VALID_REASON
    assert result.observed_value == Decimal("10")
    assert result.limit_value == Decimal("100")
    assert result.unit == "quantity"
    assert result.evaluated_at == NOW


async def test_order_quantity_limit_rule_allows_exact_quantity_boundaries() -> None:
    rule = OrderQuantityLimitRule(max_state_age=timedelta(seconds=5))
    context = RiskContext(
        evaluated_at=NOW,
        quantity_limits={
            CONTRACT_ID: RiskQuantityLimitsState(
                min_quantity=Decimal("5"),
                max_quantity=Decimal("25"),
                quantity_increment=Decimal("5"),
                observed_at=NOW,
            )
        },
    )

    lower = await rule.evaluate(_intent(quantity="5"), context)
    upper = await rule.evaluate(_intent(quantity="25"), context)

    assert lower.passed is True
    assert lower.reason_code == RISK_ORDER_QUANTITY_VALID_REASON
    assert upper.passed is True
    assert upper.reason_code == RISK_ORDER_QUANTITY_VALID_REASON


async def test_order_quantity_limit_rule_rejects_missing_quantity_limits() -> None:
    result = await OrderQuantityLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10"),
        RiskContext(evaluated_at=NOW),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ORDER_QUANTITY_LIMITS_MISSING_REASON
    assert result.observed_value == Decimal("10")
    assert result.limit_value is None
    assert result.unit == "quantity"


async def test_order_quantity_limit_rule_rejects_stale_quantity_limits() -> None:
    result = await OrderQuantityLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10"),
        RiskContext(
            evaluated_at=NOW,
            quantity_limits={
                CONTRACT_ID: RiskQuantityLimitsState(
                    min_quantity=Decimal("1"),
                    max_quantity=Decimal("100"),
                    quantity_increment=Decimal("1"),
                    observed_at=NOW - timedelta(seconds=5, milliseconds=1),
                )
            },
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ORDER_QUANTITY_LIMITS_STALE_REASON
    assert result.observed_value == Decimal("5001")
    assert result.limit_value == Decimal("5000")
    assert result.unit == "milliseconds"


async def test_order_quantity_limit_rule_rejects_future_quantity_limits() -> None:
    result = await OrderQuantityLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10"),
        RiskContext(
            evaluated_at=NOW,
            quantity_limits={
                CONTRACT_ID: RiskQuantityLimitsState(
                    min_quantity=Decimal("1"),
                    max_quantity=Decimal("100"),
                    quantity_increment=Decimal("1"),
                    observed_at=NOW + timedelta(milliseconds=1),
                )
            },
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ORDER_QUANTITY_LIMITS_FUTURE_REASON
    assert result.observed_value == Decimal("1")
    assert result.limit_value == Decimal("0")
    assert result.unit == "milliseconds"


async def test_order_quantity_limit_rule_rejects_out_of_bounds_quantities() -> None:
    rule = OrderQuantityLimitRule(max_state_age=timedelta(seconds=5))
    context = RiskContext(
        evaluated_at=NOW,
        quantity_limits={
            CONTRACT_ID: RiskQuantityLimitsState(
                min_quantity=Decimal("5"),
                max_quantity=Decimal("25"),
                quantity_increment=Decimal("1"),
                observed_at=NOW,
            )
        },
    )

    below = await rule.evaluate(_intent(quantity="4"), context)
    above = await rule.evaluate(_intent(quantity="26"), context)

    assert below.passed is False
    assert below.reason_code == RISK_ORDER_QUANTITY_BELOW_MIN_REASON
    assert below.observed_value == Decimal("4")
    assert below.limit_value == Decimal("5")
    assert below.unit == "min_quantity"
    assert above.passed is False
    assert above.reason_code == RISK_ORDER_QUANTITY_ABOVE_MAX_REASON
    assert above.observed_value == Decimal("26")
    assert above.limit_value == Decimal("25")
    assert above.unit == "max_quantity"


async def test_order_quantity_limit_rule_rejects_off_increment_quantity() -> None:
    result = await OrderQuantityLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="12"),
        RiskContext(
            evaluated_at=NOW,
            quantity_limits={
                CONTRACT_ID: RiskQuantityLimitsState(
                    min_quantity=Decimal("5"),
                    max_quantity=Decimal("25"),
                    quantity_increment=Decimal("5"),
                    observed_at=NOW,
                )
            },
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ORDER_QUANTITY_OFF_INCREMENT_REASON
    assert result.observed_value == Decimal("12")
    assert result.limit_value == Decimal("5")
    assert result.unit == "quantity_increment"


def test_risk_context_quantity_limits_are_immutable_and_validate_inputs() -> None:
    context = RiskContext(
        evaluated_at=NOW,
        quantity_limits={
            CONTRACT_ID: RiskQuantityLimitsState(
                min_quantity=Decimal("1"),
                max_quantity=Decimal("100"),
                quantity_increment=Decimal("1"),
                observed_at=NOW,
            )
        },
    )

    with pytest.raises(TypeError, match="does not support item assignment"):
        context.quantity_limits[CONTRACT_ID] = RiskQuantityLimitsState(
            min_quantity=Decimal("1"),
            max_quantity=Decimal("100"),
            quantity_increment=Decimal("1"),
            observed_at=NOW,
        )
    with pytest.raises(TypeError, match="quantity_limits"):
        RiskContext(evaluated_at=NOW, quantity_limits=())  # type: ignore[arg-type]
    with pytest.raises(RiskConfigurationError, match="ContractId"):
        RiskContext(
            evaluated_at=NOW,
            quantity_limits={
                "ctr_risk_order_quantity": RiskQuantityLimitsState(
                    min_quantity=Decimal("1"),
                    max_quantity=Decimal("100"),
                    quantity_increment=Decimal("1"),
                    observed_at=NOW,
                )
            },  # type: ignore[dict-item]
        )
    with pytest.raises(RiskConfigurationError, match="RiskQuantityLimitsState"):
        RiskContext(
            evaluated_at=NOW,
            quantity_limits={CONTRACT_ID: True},  # type: ignore[dict-item]
        )
    with pytest.raises(TypeError, match="float"):
        RiskQuantityLimitsState(
            min_quantity=1.0,  # type: ignore[arg-type]
            max_quantity=Decimal("100"),
            quantity_increment=Decimal("1"),
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="min_quantity"):
        RiskQuantityLimitsState(
            min_quantity=Decimal("-1"),
            max_quantity=Decimal("100"),
            quantity_increment=Decimal("1"),
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="max_quantity"):
        RiskQuantityLimitsState(
            min_quantity=Decimal("10"),
            max_quantity=Decimal("9"),
            quantity_increment=Decimal("1"),
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="quantity_increment"):
        RiskQuantityLimitsState(
            min_quantity=Decimal("1"),
            max_quantity=Decimal("100"),
            quantity_increment=Decimal("0"),
            observed_at=NOW,
        )


def test_order_quantity_limit_rule_rejects_invalid_configuration() -> None:
    with pytest.raises(RiskConfigurationError, match="max_state_age"):
        OrderQuantityLimitRule(max_state_age=timedelta(0))
    with pytest.raises(TypeError, match="timedelta"):
        OrderQuantityLimitRule(max_state_age=5)  # type: ignore[arg-type]


async def test_order_quantity_limit_rule_rejects_invalid_evaluation_inputs() -> None:
    rule = OrderQuantityLimitRule(max_state_age=timedelta(seconds=5))

    with pytest.raises(RiskInputError, match="OrderIntent"):
        await rule.evaluate("intent", RiskContext(evaluated_at=NOW))  # type: ignore[arg-type]
    with pytest.raises(RiskInputError, match="RiskContext"):
        await rule.evaluate(_intent(quantity="10"), "context")  # type: ignore[arg-type]


def _intent(*, quantity: str) -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_risk_order_quantity",
            "strategy_id": STRATEGY_ID,
            "market_id": MARKET_ID,
            "contract_id": CONTRACT_ID,
            "outcome_id": "out_yes",
            "side": Side.BUY,
            "quantity": quantity,
            "limit_price": "0.43",
            "order_type": OrderType.LIMIT,
            "time_in_force": TimeInForce.GTC,
            "post_only": False,
            "reduce_only": False,
            "urgency": "0.75",
            "created_at": NOW,
            "expires_at": NOW + timedelta(seconds=5),
            "signal_ids": (),
            "correlation_id": "corr_risk_order_quantity",
            "idempotency_key": "idem-risk-order-quantity",
        }
    )
