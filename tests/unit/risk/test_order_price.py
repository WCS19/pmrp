"""Unit tests for the RISK-006 order-price validation rule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.risk import (
    RISK_ORDER_PRICE_ABOVE_MAX_REASON,
    RISK_ORDER_PRICE_BELOW_MIN_REASON,
    RISK_ORDER_PRICE_BOUNDS_FUTURE_REASON,
    RISK_ORDER_PRICE_BOUNDS_MISSING_REASON,
    RISK_ORDER_PRICE_BOUNDS_STALE_REASON,
    RISK_ORDER_PRICE_NOT_REQUIRED_REASON,
    RISK_ORDER_PRICE_OFF_TICK_REASON,
    RISK_ORDER_PRICE_VALID_REASON,
    RISK_ORDER_PRICE_VALID_RULE_ID,
    RISK_ORDER_PRICE_VALID_RULE_VERSION,
    OrderPriceValidRule,
    RiskConfigurationError,
    RiskContext,
    RiskInputError,
    RiskPriceBoundsState,
)
from pmrp.schemas.enums import OrderType, Side, TimeInForce
from pmrp.schemas.identifiers import MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_risk_order_price")
STRATEGY_ID = StrategyId("strat_risk_order_price")


async def test_order_price_valid_rule_passes_price_within_bounds_and_tick() -> None:
    rule = OrderPriceValidRule(max_state_age=timedelta(seconds=5))
    result = await rule.evaluate(
        _intent(limit_price="0.43"),
        RiskContext(
            evaluated_at=NOW,
            price_bounds={
                MARKET_ID: RiskPriceBoundsState(
                    min_price=Decimal("0"),
                    max_price=Decimal("1"),
                    tick_size=Decimal("0.01"),
                    observed_at=NOW - timedelta(seconds=1),
                )
            },
        ),
    )

    assert rule.rule_id == RISK_ORDER_PRICE_VALID_RULE_ID
    assert rule.version == RISK_ORDER_PRICE_VALID_RULE_VERSION
    assert result.passed is True
    assert result.rule_id == "RISK-006"
    assert result.rule_version == "1.0"
    assert result.reason_code == RISK_ORDER_PRICE_VALID_REASON
    assert result.observed_value == Decimal("0.43")
    assert result.limit_value == Decimal("1")
    assert result.unit == "price"
    assert result.evaluated_at == NOW


async def test_order_price_valid_rule_allows_exact_price_boundaries() -> None:
    rule = OrderPriceValidRule(max_state_age=timedelta(seconds=5))
    context = RiskContext(
        evaluated_at=NOW,
        price_bounds={
            MARKET_ID: RiskPriceBoundsState(
                min_price=Decimal("0.01"),
                max_price=Decimal("0.99"),
                tick_size=Decimal("0.01"),
                observed_at=NOW,
            )
        },
    )

    lower = await rule.evaluate(_intent(limit_price="0.01"), context)
    upper = await rule.evaluate(_intent(limit_price="0.99"), context)

    assert lower.passed is True
    assert lower.reason_code == RISK_ORDER_PRICE_VALID_REASON
    assert upper.passed is True
    assert upper.reason_code == RISK_ORDER_PRICE_VALID_REASON


async def test_order_price_valid_rule_passes_market_order_without_price() -> None:
    result = await OrderPriceValidRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(limit_price=None, order_type=OrderType.MARKET),
        RiskContext(evaluated_at=NOW),
    )

    assert result.passed is True
    assert result.reason_code == RISK_ORDER_PRICE_NOT_REQUIRED_REASON
    assert result.observed_value is None
    assert result.limit_value is None
    assert result.unit == "price"


async def test_order_price_valid_rule_rejects_missing_price_bounds() -> None:
    result = await OrderPriceValidRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(limit_price="0.43"),
        RiskContext(evaluated_at=NOW),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ORDER_PRICE_BOUNDS_MISSING_REASON
    assert result.observed_value == Decimal("0.43")
    assert result.limit_value is None
    assert result.unit == "price"


async def test_order_price_valid_rule_rejects_stale_price_bounds() -> None:
    result = await OrderPriceValidRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(limit_price="0.43"),
        RiskContext(
            evaluated_at=NOW,
            price_bounds={
                MARKET_ID: RiskPriceBoundsState(
                    min_price=Decimal("0"),
                    max_price=Decimal("1"),
                    observed_at=NOW - timedelta(seconds=5, milliseconds=1),
                )
            },
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ORDER_PRICE_BOUNDS_STALE_REASON
    assert result.observed_value == Decimal("5001")
    assert result.limit_value == Decimal("5000")
    assert result.unit == "milliseconds"


async def test_order_price_valid_rule_rejects_future_price_bounds() -> None:
    result = await OrderPriceValidRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(limit_price="0.43"),
        RiskContext(
            evaluated_at=NOW,
            price_bounds={
                MARKET_ID: RiskPriceBoundsState(
                    min_price=Decimal("0"),
                    max_price=Decimal("1"),
                    observed_at=NOW + timedelta(milliseconds=1),
                )
            },
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ORDER_PRICE_BOUNDS_FUTURE_REASON
    assert result.observed_value == Decimal("1")
    assert result.limit_value == Decimal("0")
    assert result.unit == "milliseconds"


async def test_order_price_valid_rule_rejects_out_of_bounds_prices() -> None:
    rule = OrderPriceValidRule(max_state_age=timedelta(seconds=5))
    context = RiskContext(
        evaluated_at=NOW,
        price_bounds={
            MARKET_ID: RiskPriceBoundsState(
                min_price=Decimal("0.10"),
                max_price=Decimal("0.90"),
                observed_at=NOW,
            )
        },
    )

    below = await rule.evaluate(_intent(limit_price="0.09"), context)
    above = await rule.evaluate(_intent(limit_price="0.91"), context)

    assert below.passed is False
    assert below.reason_code == RISK_ORDER_PRICE_BELOW_MIN_REASON
    assert below.observed_value == Decimal("0.09")
    assert below.limit_value == Decimal("0.10")
    assert below.unit == "min_price"
    assert above.passed is False
    assert above.reason_code == RISK_ORDER_PRICE_ABOVE_MAX_REASON
    assert above.observed_value == Decimal("0.91")
    assert above.limit_value == Decimal("0.90")
    assert above.unit == "max_price"


async def test_order_price_valid_rule_rejects_off_tick_price() -> None:
    result = await OrderPriceValidRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(limit_price="0.43"),
        RiskContext(
            evaluated_at=NOW,
            price_bounds={
                MARKET_ID: RiskPriceBoundsState(
                    min_price=Decimal("0"),
                    max_price=Decimal("1"),
                    tick_size=Decimal("0.05"),
                    observed_at=NOW,
                )
            },
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_ORDER_PRICE_OFF_TICK_REASON
    assert result.observed_value == Decimal("0.43")
    assert result.limit_value == Decimal("0.05")
    assert result.unit == "tick_size"


def test_risk_context_price_bounds_are_immutable_and_validate_inputs() -> None:
    context = RiskContext(
        evaluated_at=NOW,
        price_bounds={
            MARKET_ID: RiskPriceBoundsState(
                min_price=Decimal("0"),
                max_price=Decimal("1"),
                observed_at=NOW,
            )
        },
    )

    with pytest.raises(TypeError, match="does not support item assignment"):
        context.price_bounds[MARKET_ID] = RiskPriceBoundsState(
            min_price=Decimal("0"),
            max_price=Decimal("1"),
            observed_at=NOW,
        )
    with pytest.raises(TypeError, match="price_bounds"):
        RiskContext(evaluated_at=NOW, price_bounds=())  # type: ignore[arg-type]
    with pytest.raises(RiskConfigurationError, match="MarketId"):
        RiskContext(
            evaluated_at=NOW,
            price_bounds={
                "mkt_risk_order_price": RiskPriceBoundsState(
                    min_price=Decimal("0"),
                    max_price=Decimal("1"),
                    observed_at=NOW,
                )
            },  # type: ignore[dict-item]
        )
    with pytest.raises(RiskConfigurationError, match="RiskPriceBoundsState"):
        RiskContext(
            evaluated_at=NOW,
            price_bounds={MARKET_ID: True},  # type: ignore[dict-item]
        )
    with pytest.raises(TypeError, match="float"):
        RiskPriceBoundsState(
            min_price=0.0,  # type: ignore[arg-type]
            max_price=Decimal("1"),
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="min_price"):
        RiskPriceBoundsState(
            min_price=Decimal("-0.01"),
            max_price=Decimal("1"),
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="max_price"):
        RiskPriceBoundsState(
            min_price=Decimal("0.50"),
            max_price=Decimal("0.49"),
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="tick_size"):
        RiskPriceBoundsState(
            min_price=Decimal("0"),
            max_price=Decimal("1"),
            tick_size=Decimal("0"),
            observed_at=NOW,
        )


def test_order_price_valid_rule_rejects_invalid_configuration() -> None:
    with pytest.raises(RiskConfigurationError, match="max_state_age"):
        OrderPriceValidRule(max_state_age=timedelta(0))
    with pytest.raises(TypeError, match="timedelta"):
        OrderPriceValidRule(max_state_age=5)  # type: ignore[arg-type]


async def test_order_price_valid_rule_rejects_invalid_evaluation_inputs() -> None:
    rule = OrderPriceValidRule(max_state_age=timedelta(seconds=5))

    with pytest.raises(RiskInputError, match="OrderIntent"):
        await rule.evaluate("intent", RiskContext(evaluated_at=NOW))  # type: ignore[arg-type]
    with pytest.raises(RiskInputError, match="RiskContext"):
        await rule.evaluate(_intent(limit_price="0.43"), "context")  # type: ignore[arg-type]


def _intent(
    *,
    limit_price: str | None,
    order_type: OrderType = OrderType.LIMIT,
) -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_risk_order_price",
            "strategy_id": STRATEGY_ID,
            "market_id": MARKET_ID,
            "contract_id": "ctr_risk_order_price",
            "outcome_id": "out_yes",
            "side": Side.BUY,
            "quantity": "10",
            "limit_price": limit_price,
            "order_type": order_type,
            "time_in_force": TimeInForce.GTC,
            "post_only": False,
            "reduce_only": False,
            "urgency": "0.75",
            "created_at": NOW,
            "expires_at": NOW + timedelta(seconds=5),
            "signal_ids": (),
            "correlation_id": "corr_risk_order_price",
            "idempotency_key": "idem-risk-order-price",
        }
    )
