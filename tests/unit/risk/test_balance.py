"""Unit tests for the RISK-017 available-balance rule."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.risk import (
    RISK_AVAILABLE_BALANCE_INSUFFICIENT_REASON,
    RISK_AVAILABLE_BALANCE_PRICE_MISSING_REASON,
    RISK_AVAILABLE_BALANCE_RULE_ID,
    RISK_AVAILABLE_BALANCE_RULE_VERSION,
    RISK_AVAILABLE_BALANCE_STATE_FUTURE_REASON,
    RISK_AVAILABLE_BALANCE_STATE_MISSING_REASON,
    RISK_AVAILABLE_BALANCE_STATE_STALE_REASON,
    RISK_AVAILABLE_BALANCE_VALID_REASON,
    AvailableBalanceRule,
    RiskAvailableBalanceState,
    RiskConfigurationError,
    RiskContext,
    RiskInputError,
)
from pmrp.schemas.enums import OrderType, Side, TimeInForce
from pmrp.schemas.identifiers import ContractId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_risk_available_balance")
CONTRACT_ID = ContractId("ctr_risk_available_balance")
STRATEGY_ID = StrategyId("strat_risk_available_balance")


async def test_available_balance_rule_passes_required_balance_under_available() -> None:
    rule = AvailableBalanceRule(max_state_age=timedelta(seconds=5))
    result = await rule.evaluate(
        _intent(quantity="10", limit_price="0.40"),
        RiskContext(
            evaluated_at=NOW,
            available_balance=RiskAvailableBalanceState(
                available_balance=Decimal("5"),
                observed_at=NOW - timedelta(seconds=1),
            ),
        ),
    )

    assert rule.rule_id == RISK_AVAILABLE_BALANCE_RULE_ID
    assert rule.version == RISK_AVAILABLE_BALANCE_RULE_VERSION
    assert result.passed is True
    assert result.rule_id == "RISK-017"
    assert result.rule_version == "1.0"
    assert result.reason_code == RISK_AVAILABLE_BALANCE_VALID_REASON
    assert result.observed_value == Decimal("4.00")
    assert result.limit_value == Decimal("5")
    assert result.unit == "balance"
    assert result.evaluated_at == NOW


async def test_available_balance_rule_allows_exact_available_boundary() -> None:
    result = await AvailableBalanceRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price="0.50"),
        RiskContext(
            evaluated_at=NOW,
            available_balance=RiskAvailableBalanceState(
                available_balance=Decimal("5"),
                observed_at=NOW,
            ),
        ),
    )

    assert result.passed is True
    assert result.reason_code == RISK_AVAILABLE_BALANCE_VALID_REASON
    assert result.observed_value == Decimal("5.00")
    assert result.limit_value == Decimal("5")


async def test_available_balance_rule_counts_sell_notional_as_required_balance() -> None:
    result = await AvailableBalanceRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price="0.50", side=Side.SELL),
        RiskContext(
            evaluated_at=NOW,
            available_balance=RiskAvailableBalanceState(
                available_balance=Decimal("5"),
                observed_at=NOW,
            ),
        ),
    )

    assert result.passed is True
    assert result.reason_code == RISK_AVAILABLE_BALANCE_VALID_REASON
    assert result.observed_value == Decimal("5.00")


async def test_available_balance_rule_subtracts_reserved_balance() -> None:
    result = await AvailableBalanceRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price="0.50"),
        RiskContext(
            evaluated_at=NOW,
            available_balance=RiskAvailableBalanceState(
                available_balance=Decimal("7"),
                reserved_balance=Decimal("2"),
                observed_at=NOW,
            ),
        ),
    )

    assert result.passed is True
    assert result.reason_code == RISK_AVAILABLE_BALANCE_VALID_REASON
    assert result.observed_value == Decimal("5.00")
    assert result.limit_value == Decimal("5")


async def test_available_balance_rule_rejects_missing_limit_price() -> None:
    result = await AvailableBalanceRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price=None, order_type=OrderType.MARKET),
        RiskContext(evaluated_at=NOW),
    )

    assert result.passed is False
    assert result.reason_code == RISK_AVAILABLE_BALANCE_PRICE_MISSING_REASON
    assert result.observed_value is None
    assert result.limit_value is None
    assert result.unit == "balance"


async def test_available_balance_rule_rejects_missing_available_balance_state() -> None:
    result = await AvailableBalanceRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price="0.50"),
        RiskContext(evaluated_at=NOW),
    )

    assert result.passed is False
    assert result.reason_code == RISK_AVAILABLE_BALANCE_STATE_MISSING_REASON
    assert result.observed_value == Decimal("5.00")
    assert result.limit_value is None
    assert result.unit == "balance"


async def test_available_balance_rule_rejects_stale_available_balance_state() -> None:
    result = await AvailableBalanceRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price="0.50"),
        RiskContext(
            evaluated_at=NOW,
            available_balance=RiskAvailableBalanceState(
                available_balance=Decimal("5"),
                observed_at=NOW - timedelta(seconds=5, milliseconds=1),
            ),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_AVAILABLE_BALANCE_STATE_STALE_REASON
    assert result.observed_value == Decimal("5001")
    assert result.limit_value == Decimal("5000")
    assert result.unit == "milliseconds"


async def test_available_balance_rule_rejects_future_available_balance_state() -> None:
    result = await AvailableBalanceRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price="0.50"),
        RiskContext(
            evaluated_at=NOW,
            available_balance=RiskAvailableBalanceState(
                available_balance=Decimal("5"),
                observed_at=NOW + timedelta(milliseconds=1),
            ),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_AVAILABLE_BALANCE_STATE_FUTURE_REASON
    assert result.observed_value == Decimal("1")
    assert result.limit_value == Decimal("0")
    assert result.unit == "milliseconds"


async def test_available_balance_rule_rejects_insufficient_available_balance() -> None:
    result = await AvailableBalanceRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price="0.51"),
        RiskContext(
            evaluated_at=NOW,
            available_balance=RiskAvailableBalanceState(
                available_balance=Decimal("5"),
                observed_at=NOW,
            ),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_AVAILABLE_BALANCE_INSUFFICIENT_REASON
    assert result.observed_value == Decimal("5.10")
    assert result.limit_value == Decimal("5")
    assert result.unit == "balance"


def test_risk_context_available_balance_validates_inputs() -> None:
    context = RiskContext(
        evaluated_at=NOW,
        available_balance=RiskAvailableBalanceState(
            available_balance=Decimal("7"),
            reserved_balance=Decimal("2"),
            observed_at=NOW,
        ),
    )

    assert context.available_balance_state() == context.available_balance
    assert context.available_balance_state().effective_available_balance == Decimal("5")
    with pytest.raises(FrozenInstanceError):
        context.available_balance = RiskAvailableBalanceState(
            available_balance=Decimal("5"),
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="RiskAvailableBalanceState"):
        RiskContext(evaluated_at=NOW, available_balance=True)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="float"):
        RiskAvailableBalanceState(
            available_balance=5.0,  # type: ignore[arg-type]
            observed_at=NOW,
        )
    with pytest.raises(TypeError, match="float"):
        RiskAvailableBalanceState(
            available_balance=Decimal("5"),
            reserved_balance=1.0,  # type: ignore[arg-type]
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="reserved_balance"):
        RiskAvailableBalanceState(
            available_balance=Decimal("5"),
            reserved_balance=Decimal("-0.01"),
            observed_at=NOW,
        )


async def test_available_balance_rule_rejects_negative_effective_available_balance() -> None:
    result = await AvailableBalanceRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="1", limit_price="0.01"),
        RiskContext(
            evaluated_at=NOW,
            available_balance=RiskAvailableBalanceState(
                available_balance=Decimal("-1"),
                observed_at=NOW,
            ),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_AVAILABLE_BALANCE_INSUFFICIENT_REASON
    assert result.observed_value == Decimal("0.01")
    assert result.limit_value == Decimal("-1")


async def test_available_balance_rule_rejects_invalid_configuration_and_inputs() -> None:
    rule = AvailableBalanceRule(max_state_age=timedelta(seconds=5))

    with pytest.raises(RiskConfigurationError, match="max_state_age"):
        AvailableBalanceRule(max_state_age=timedelta(0))
    with pytest.raises(TypeError, match="max_state_age"):
        AvailableBalanceRule(max_state_age=5)  # type: ignore[arg-type]
    with pytest.raises(RiskInputError, match="OrderIntent"):
        await rule.evaluate(object(), RiskContext(evaluated_at=NOW))  # type: ignore[arg-type]
    with pytest.raises(RiskInputError, match="RiskContext"):
        await rule.evaluate(_intent(), object())  # type: ignore[arg-type]


def _intent(
    *,
    quantity: str = "10",
    limit_price: str | None = "0.50",
    order_type: OrderType = OrderType.LIMIT,
    side: Side = Side.BUY,
) -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_risk_available_balance",
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
            "correlation_id": "corr_risk_available_balance",
            "idempotency_key": "idem-risk-available-balance",
        }
    )
