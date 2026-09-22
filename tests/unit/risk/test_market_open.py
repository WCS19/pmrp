"""Unit tests for the RISK-004 market-open rule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.risk import (
    RISK_MARKET_NOT_OPEN_REASON,
    RISK_MARKET_OPEN_REASON,
    RISK_MARKET_OPEN_RULE_ID,
    RISK_MARKET_OPEN_RULE_VERSION,
    RISK_MARKET_STATUS_FUTURE_REASON,
    RISK_MARKET_STATUS_MISSING_REASON,
    RISK_MARKET_STATUS_STALE_REASON,
    MarketOpenRule,
    RiskConfigurationError,
    RiskContext,
    RiskInputError,
    RiskMarketStatusState,
)
from pmrp.schemas.enums import MarketStatus, OrderType, Side, TimeInForce
from pmrp.schemas.identifiers import MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_risk_market_open")
STRATEGY_ID = StrategyId("strat_risk_market_open")


async def test_market_open_rule_passes_open_market() -> None:
    rule = MarketOpenRule(max_state_age=timedelta(seconds=5))
    result = await rule.evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            market_status={
                MARKET_ID: RiskMarketStatusState(
                    status=MarketStatus.OPEN,
                    observed_at=NOW - timedelta(seconds=1),
                )
            },
        ),
    )

    assert rule.rule_id == RISK_MARKET_OPEN_RULE_ID
    assert rule.version == RISK_MARKET_OPEN_RULE_VERSION
    assert result.passed is True
    assert result.rule_id == "RISK-004"
    assert result.rule_version == "1.0"
    assert result.reason_code == RISK_MARKET_OPEN_REASON
    assert result.observed_value == Decimal("1")
    assert result.limit_value == Decimal("1")
    assert result.unit == "open_status"
    assert result.evaluated_at == NOW


async def test_market_open_rule_rejects_non_open_market() -> None:
    result = await MarketOpenRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            market_status={
                MARKET_ID: RiskMarketStatusState(
                    status=MarketStatus.HALTED,
                    observed_at=NOW - timedelta(seconds=1),
                )
            },
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_MARKET_NOT_OPEN_REASON
    assert result.observed_value == Decimal("0")
    assert result.limit_value == Decimal("1")
    assert result.unit == "open_status"


async def test_market_open_rule_can_accept_configured_open_statuses() -> None:
    result = await MarketOpenRule(
        max_state_age=timedelta(seconds=5),
        open_statuses=(MarketStatus.OPEN, MarketStatus.HALTED),
    ).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            market_status={
                MARKET_ID: RiskMarketStatusState(
                    status=MarketStatus.HALTED,
                    observed_at=NOW - timedelta(seconds=1),
                )
            },
        ),
    )

    assert result.passed is True
    assert result.reason_code == RISK_MARKET_OPEN_REASON
    assert result.observed_value == Decimal("1")


async def test_market_open_rule_allows_exact_staleness_boundary() -> None:
    result = await MarketOpenRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            market_status={
                MARKET_ID: RiskMarketStatusState(
                    status=MarketStatus.OPEN,
                    observed_at=NOW - timedelta(seconds=5),
                )
            },
        ),
    )

    assert result.passed is True
    assert result.reason_code == RISK_MARKET_OPEN_REASON


async def test_market_open_rule_rejects_missing_market_status() -> None:
    result = await MarketOpenRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(evaluated_at=NOW),
    )

    assert result.passed is False
    assert result.reason_code == RISK_MARKET_STATUS_MISSING_REASON
    assert result.observed_value is None
    assert result.limit_value == Decimal("1")
    assert result.unit == "open_status"


async def test_market_open_rule_rejects_stale_market_status() -> None:
    result = await MarketOpenRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            market_status={
                MARKET_ID: RiskMarketStatusState(
                    status=MarketStatus.OPEN,
                    observed_at=NOW - timedelta(seconds=5, milliseconds=1),
                )
            },
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_MARKET_STATUS_STALE_REASON
    assert result.observed_value == Decimal("5001")
    assert result.limit_value == Decimal("5000")
    assert result.unit == "milliseconds"


async def test_market_open_rule_rejects_future_market_status() -> None:
    result = await MarketOpenRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            market_status={
                MARKET_ID: RiskMarketStatusState(
                    status=MarketStatus.OPEN,
                    observed_at=NOW + timedelta(milliseconds=1),
                )
            },
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_MARKET_STATUS_FUTURE_REASON
    assert result.observed_value == Decimal("1")
    assert result.limit_value == Decimal("0")
    assert result.unit == "milliseconds"


def test_risk_context_market_status_is_immutable_and_validates_inputs() -> None:
    context = RiskContext(
        evaluated_at=NOW,
        market_status={
            MARKET_ID: RiskMarketStatusState(
                status=MarketStatus.OPEN,
                observed_at=NOW,
            )
        },
    )

    with pytest.raises(TypeError, match="does not support item assignment"):
        context.market_status[MARKET_ID] = RiskMarketStatusState(
            status=MarketStatus.CLOSED,
            observed_at=NOW,
        )
    with pytest.raises(TypeError, match="market_status"):
        RiskContext(evaluated_at=NOW, market_status=())  # type: ignore[arg-type]
    with pytest.raises(RiskConfigurationError, match="MarketId"):
        RiskContext(
            evaluated_at=NOW,
            market_status={
                "mkt_risk_market_open": RiskMarketStatusState(
                    status=MarketStatus.OPEN,
                    observed_at=NOW,
                )
            },  # type: ignore[dict-item]
        )
    with pytest.raises(RiskConfigurationError, match="RiskMarketStatusState"):
        RiskContext(
            evaluated_at=NOW,
            market_status={MARKET_ID: MarketStatus.OPEN},  # type: ignore[dict-item]
        )
    with pytest.raises(TypeError, match="MarketStatus"):
        RiskMarketStatusState(status="open", observed_at=NOW)  # type: ignore[arg-type]


def test_market_open_rule_rejects_invalid_configuration() -> None:
    with pytest.raises(RiskConfigurationError, match="max_state_age"):
        MarketOpenRule(max_state_age=timedelta(0))
    with pytest.raises(TypeError, match="timedelta"):
        MarketOpenRule(max_state_age=5)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="open_statuses"):
        MarketOpenRule(
            max_state_age=timedelta(seconds=5),
            open_statuses=[MarketStatus.OPEN],  # type: ignore[arg-type]
        )
    with pytest.raises(RiskConfigurationError, match="open_statuses"):
        MarketOpenRule(max_state_age=timedelta(seconds=5), open_statuses=())
    with pytest.raises(TypeError, match="MarketStatus"):
        MarketOpenRule(
            max_state_age=timedelta(seconds=5),
            open_statuses=("open",),  # type: ignore[arg-type]
        )


async def test_market_open_rule_rejects_invalid_evaluation_inputs() -> None:
    rule = MarketOpenRule(max_state_age=timedelta(seconds=5))

    with pytest.raises(RiskInputError, match="OrderIntent"):
        await rule.evaluate("intent", RiskContext(evaluated_at=NOW))  # type: ignore[arg-type]
    with pytest.raises(RiskInputError, match="RiskContext"):
        await rule.evaluate(_intent(), "context")  # type: ignore[arg-type]


def _intent() -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_risk_market_open",
            "strategy_id": STRATEGY_ID,
            "market_id": MARKET_ID,
            "contract_id": "ctr_risk_market_open",
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
            "correlation_id": "corr_risk_market_open",
            "idempotency_key": "idem-risk-market-open",
        }
    )
