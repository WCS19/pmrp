"""Unit tests for the RISK-013 exchange-capital limit rule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.risk import (
    RISK_EXCHANGE_CAPITAL_ABOVE_MAX_REASON,
    RISK_EXCHANGE_CAPITAL_EXCHANGE_MISSING_REASON,
    RISK_EXCHANGE_CAPITAL_LIMIT_RULE_ID,
    RISK_EXCHANGE_CAPITAL_LIMIT_RULE_VERSION,
    RISK_EXCHANGE_CAPITAL_PRICE_MISSING_REASON,
    RISK_EXCHANGE_CAPITAL_STATE_FUTURE_REASON,
    RISK_EXCHANGE_CAPITAL_STATE_MISSING_REASON,
    RISK_EXCHANGE_CAPITAL_STATE_STALE_REASON,
    RISK_EXCHANGE_CAPITAL_VALID_REASON,
    ExchangeCapitalLimitRule,
    RiskConfigurationError,
    RiskContext,
    RiskExchangeCapitalState,
    RiskInputError,
)
from pmrp.schemas.enums import OrderType, Side, TimeInForce
from pmrp.schemas.identifiers import ContractId, ExchangeId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
EXCHANGE_ID = ExchangeId("xchg_risk_exchange_capital")
MARKET_ID = MarketId("mkt_risk_exchange_capital")
CONTRACT_ID = ContractId("ctr_risk_exchange_capital")
STRATEGY_ID = StrategyId("strat_risk_exchange_capital")


async def test_exchange_capital_limit_rule_passes_projected_capital_under_cap() -> None:
    rule = ExchangeCapitalLimitRule(max_state_age=timedelta(seconds=5))
    result = await rule.evaluate(
        _intent(quantity="10", limit_price="0.40"),
        _context(
            current_capital_used=Decimal("15"),
            max_exchange_capital=Decimal("25"),
            observed_at=NOW - timedelta(seconds=1),
        ),
    )

    assert rule.rule_id == RISK_EXCHANGE_CAPITAL_LIMIT_RULE_ID
    assert rule.version == RISK_EXCHANGE_CAPITAL_LIMIT_RULE_VERSION
    assert result.passed is True
    assert result.rule_id == "RISK-013"
    assert result.rule_version == "1.0"
    assert result.reason_code == RISK_EXCHANGE_CAPITAL_VALID_REASON
    assert result.observed_value == Decimal("19.00")
    assert result.limit_value == Decimal("25")
    assert result.unit == "capital"
    assert result.evaluated_at == NOW


async def test_exchange_capital_limit_rule_allows_exact_cap_boundary() -> None:
    result = await ExchangeCapitalLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price="0.50"),
        _context(
            current_capital_used=Decimal("15"),
            max_exchange_capital=Decimal("20"),
            observed_at=NOW,
        ),
    )

    assert result.passed is True
    assert result.reason_code == RISK_EXCHANGE_CAPITAL_VALID_REASON
    assert result.observed_value == Decimal("20.00")
    assert result.limit_value == Decimal("20")


async def test_exchange_capital_limit_rule_counts_sell_notional_as_capital_usage() -> None:
    result = await ExchangeCapitalLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price="0.50", side=Side.SELL),
        _context(
            current_capital_used=Decimal("15"),
            max_exchange_capital=Decimal("20"),
            observed_at=NOW,
        ),
    )

    assert result.passed is True
    assert result.reason_code == RISK_EXCHANGE_CAPITAL_VALID_REASON
    assert result.observed_value == Decimal("20.00")


async def test_exchange_capital_limit_rule_includes_open_orders_and_reservations() -> None:
    result = await ExchangeCapitalLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price="0.50"),
        _context(
            current_capital_used=Decimal("10"),
            open_order_capital=Decimal("3"),
            reserved_capital=Decimal("2"),
            max_exchange_capital=Decimal("20"),
            observed_at=NOW,
        ),
    )

    assert result.passed is True
    assert result.reason_code == RISK_EXCHANGE_CAPITAL_VALID_REASON
    assert result.observed_value == Decimal("20.00")
    assert result.limit_value == Decimal("20")


async def test_exchange_capital_limit_rule_rejects_missing_limit_price() -> None:
    result = await ExchangeCapitalLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price=None, order_type=OrderType.MARKET),
        RiskContext(evaluated_at=NOW),
    )

    assert result.passed is False
    assert result.reason_code == RISK_EXCHANGE_CAPITAL_PRICE_MISSING_REASON
    assert result.observed_value is None
    assert result.limit_value is None
    assert result.unit == "capital"


async def test_exchange_capital_limit_rule_rejects_missing_market_exchange() -> None:
    result = await ExchangeCapitalLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price="0.50"),
        RiskContext(
            evaluated_at=NOW,
            exchange_capital={
                EXCHANGE_ID: RiskExchangeCapitalState(
                    current_capital_used=Decimal("15"),
                    max_exchange_capital=Decimal("25"),
                    observed_at=NOW,
                )
            },
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_EXCHANGE_CAPITAL_EXCHANGE_MISSING_REASON
    assert result.observed_value == Decimal("5.00")
    assert result.limit_value is None
    assert result.unit == "capital"


async def test_exchange_capital_limit_rule_rejects_missing_exchange_capital_state() -> None:
    result = await ExchangeCapitalLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price="0.50"),
        RiskContext(evaluated_at=NOW, market_exchanges={MARKET_ID: EXCHANGE_ID}),
    )

    assert result.passed is False
    assert result.reason_code == RISK_EXCHANGE_CAPITAL_STATE_MISSING_REASON
    assert result.observed_value == Decimal("5.00")
    assert result.limit_value is None
    assert result.unit == "capital"


async def test_exchange_capital_limit_rule_rejects_stale_exchange_capital_state() -> None:
    result = await ExchangeCapitalLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price="0.50"),
        _context(
            current_capital_used=Decimal("15"),
            max_exchange_capital=Decimal("25"),
            observed_at=NOW - timedelta(seconds=5, milliseconds=1),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_EXCHANGE_CAPITAL_STATE_STALE_REASON
    assert result.observed_value == Decimal("5001")
    assert result.limit_value == Decimal("5000")
    assert result.unit == "milliseconds"


async def test_exchange_capital_limit_rule_rejects_future_exchange_capital_state() -> None:
    result = await ExchangeCapitalLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price="0.50"),
        _context(
            current_capital_used=Decimal("15"),
            max_exchange_capital=Decimal("25"),
            observed_at=NOW + timedelta(milliseconds=1),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_EXCHANGE_CAPITAL_STATE_FUTURE_REASON
    assert result.observed_value == Decimal("1")
    assert result.limit_value == Decimal("0")
    assert result.unit == "milliseconds"


async def test_exchange_capital_limit_rule_rejects_capital_above_cap() -> None:
    result = await ExchangeCapitalLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price="0.51"),
        _context(
            current_capital_used=Decimal("15"),
            max_exchange_capital=Decimal("20"),
            observed_at=NOW,
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_EXCHANGE_CAPITAL_ABOVE_MAX_REASON
    assert result.observed_value == Decimal("20.10")
    assert result.limit_value == Decimal("20")
    assert result.unit == "capital"


def test_risk_context_exchange_capital_is_immutable_and_validates_inputs() -> None:
    context = _context(
        current_capital_used=Decimal("15"),
        max_exchange_capital=Decimal("25"),
        observed_at=NOW,
    )

    with pytest.raises(TypeError, match="does not support item assignment"):
        context.market_exchanges[MARKET_ID] = EXCHANGE_ID
    with pytest.raises(TypeError, match="does not support item assignment"):
        context.exchange_capital[EXCHANGE_ID] = RiskExchangeCapitalState(
            current_capital_used=Decimal("15"),
            max_exchange_capital=Decimal("25"),
            observed_at=NOW,
        )
    with pytest.raises(TypeError, match="market_exchanges"):
        RiskContext(evaluated_at=NOW, market_exchanges=())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="exchange_capital"):
        RiskContext(evaluated_at=NOW, exchange_capital=())  # type: ignore[arg-type]
    with pytest.raises(RiskConfigurationError, match="MarketId"):
        RiskContext(evaluated_at=NOW, market_exchanges={"market": EXCHANGE_ID})  # type: ignore[dict-item]
    with pytest.raises(RiskConfigurationError, match="ExchangeId"):
        RiskContext(evaluated_at=NOW, market_exchanges={MARKET_ID: "kalshi"})  # type: ignore[dict-item]
    with pytest.raises(RiskConfigurationError, match="ExchangeId"):
        RiskContext(
            evaluated_at=NOW,
            exchange_capital={
                "xchg_risk_exchange_capital": RiskExchangeCapitalState(
                    current_capital_used=Decimal("15"),
                    max_exchange_capital=Decimal("25"),
                    observed_at=NOW,
                )
            },  # type: ignore[dict-item]
        )
    with pytest.raises(RiskConfigurationError, match="RiskExchangeCapitalState"):
        RiskContext(evaluated_at=NOW, exchange_capital={EXCHANGE_ID: True})  # type: ignore[dict-item]
    with pytest.raises(TypeError, match="float"):
        RiskExchangeCapitalState(
            current_capital_used=15.0,  # type: ignore[arg-type]
            max_exchange_capital=Decimal("25"),
            observed_at=NOW,
        )
    with pytest.raises(TypeError, match="float"):
        RiskExchangeCapitalState(
            current_capital_used=Decimal("15"),
            open_order_capital=1.0,  # type: ignore[arg-type]
            max_exchange_capital=Decimal("25"),
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="current_capital_used"):
        RiskExchangeCapitalState(
            current_capital_used=Decimal("-0.01"),
            max_exchange_capital=Decimal("25"),
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="open_order_capital"):
        RiskExchangeCapitalState(
            current_capital_used=Decimal("15"),
            open_order_capital=Decimal("-0.01"),
            max_exchange_capital=Decimal("25"),
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="reserved_capital"):
        RiskExchangeCapitalState(
            current_capital_used=Decimal("15"),
            reserved_capital=Decimal("-0.01"),
            max_exchange_capital=Decimal("25"),
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="max_exchange_capital"):
        RiskExchangeCapitalState(
            current_capital_used=Decimal("15"),
            max_exchange_capital=Decimal("0"),
            observed_at=NOW,
        )


async def test_exchange_capital_limit_rule_rejects_invalid_configuration_and_inputs() -> None:
    rule = ExchangeCapitalLimitRule(max_state_age=timedelta(seconds=5))

    with pytest.raises(RiskConfigurationError, match="max_state_age"):
        ExchangeCapitalLimitRule(max_state_age=timedelta(0))
    with pytest.raises(TypeError, match="max_state_age"):
        ExchangeCapitalLimitRule(max_state_age=5)  # type: ignore[arg-type]
    with pytest.raises(RiskInputError, match="OrderIntent"):
        await rule.evaluate(object(), RiskContext(evaluated_at=NOW))  # type: ignore[arg-type]
    with pytest.raises(RiskInputError, match="RiskContext"):
        await rule.evaluate(_intent(quantity="10", limit_price="0.50"), object())  # type: ignore[arg-type]


def _context(
    *,
    current_capital_used: Decimal,
    max_exchange_capital: Decimal,
    observed_at: datetime,
    open_order_capital: Decimal = Decimal("0"),
    reserved_capital: Decimal = Decimal("0"),
) -> RiskContext:
    return RiskContext(
        evaluated_at=NOW,
        market_exchanges={MARKET_ID: EXCHANGE_ID},
        exchange_capital={
            EXCHANGE_ID: RiskExchangeCapitalState(
                current_capital_used=current_capital_used,
                open_order_capital=open_order_capital,
                reserved_capital=reserved_capital,
                max_exchange_capital=max_exchange_capital,
                observed_at=observed_at,
            )
        },
    )


def _intent(
    *,
    quantity: str,
    limit_price: str | None,
    side: Side = Side.BUY,
    order_type: OrderType = OrderType.LIMIT,
) -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_risk_exchange_capital",
            "strategy_id": STRATEGY_ID,
            "market_id": MARKET_ID,
            "contract_id": CONTRACT_ID,
            "outcome_id": "out_yes",
            "side": side,
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
            "correlation_id": "corr_risk_exchange_capital",
            "idempotency_key": "idem-risk-exchange-capital",
        }
    )
