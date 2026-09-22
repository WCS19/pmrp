"""Unit tests for the RISK-019 kill-switch clear rule."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.risk import (
    RISK_KILL_SWITCH_ACTIVE_REASON,
    RISK_KILL_SWITCH_CLEAR_REASON,
    RISK_KILL_SWITCH_CLEAR_RULE_ID,
    RISK_KILL_SWITCH_CLEAR_RULE_VERSION,
    RISK_KILL_SWITCH_NOT_CLEAR_REASON,
    RISK_KILL_SWITCH_STATE_FUTURE_REASON,
    RISK_KILL_SWITCH_STATE_MISSING_REASON,
    RISK_KILL_SWITCH_STATE_STALE_REASON,
    KillSwitchClearRule,
    RiskConfigurationError,
    RiskContext,
    RiskInputError,
    RiskKillSwitchClearState,
)
from pmrp.schemas.enums import OrderType, Side, TimeInForce
from pmrp.schemas.identifiers import ContractId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.risk import KillSwitchScope

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_risk_kill_switch_clear")
CONTRACT_ID = ContractId("ctr_risk_kill_switch_clear")
STRATEGY_ID = StrategyId("strat_risk_kill_switch_clear")


async def test_kill_switch_clear_rule_passes_when_state_is_clear() -> None:
    rule = KillSwitchClearRule(max_state_age=timedelta(seconds=5))
    result = await rule.evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            kill_switch_clear=RiskKillSwitchClearState(
                clear=True,
                observed_at=NOW - timedelta(seconds=1),
            ),
        ),
    )

    assert rule.rule_id == RISK_KILL_SWITCH_CLEAR_RULE_ID
    assert rule.version == RISK_KILL_SWITCH_CLEAR_RULE_VERSION
    assert result.passed is True
    assert result.rule_id == "RISK-019"
    assert result.rule_version == "1.0"
    assert result.reason_code == RISK_KILL_SWITCH_CLEAR_REASON
    assert result.observed_value == Decimal("1")
    assert result.limit_value == Decimal("1")
    assert result.unit == "clear_flag"
    assert result.evaluated_at == NOW


async def test_kill_switch_clear_rule_rejects_active_scope() -> None:
    result = await KillSwitchClearRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            kill_switch_clear=RiskKillSwitchClearState(
                clear=False,
                active_scopes={KillSwitchScope.GLOBAL, KillSwitchScope.MARKET},
                observed_at=NOW,
            ),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_KILL_SWITCH_ACTIVE_REASON
    assert result.observed_value == Decimal("2")
    assert result.limit_value == Decimal("0")
    assert result.unit == "active_scope_count"


async def test_kill_switch_clear_rule_rejects_not_clear_without_active_scope() -> None:
    result = await KillSwitchClearRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            kill_switch_clear=RiskKillSwitchClearState(
                clear=False,
                observed_at=NOW,
            ),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_KILL_SWITCH_NOT_CLEAR_REASON
    assert result.observed_value == Decimal("0")
    assert result.limit_value == Decimal("1")
    assert result.unit == "clear_flag"


async def test_kill_switch_clear_rule_rejects_missing_state() -> None:
    result = await KillSwitchClearRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(evaluated_at=NOW),
    )

    assert result.passed is False
    assert result.reason_code == RISK_KILL_SWITCH_STATE_MISSING_REASON
    assert result.observed_value is None
    assert result.limit_value == Decimal("1")
    assert result.unit == "clear_flag"


async def test_kill_switch_clear_rule_rejects_stale_state() -> None:
    result = await KillSwitchClearRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            kill_switch_clear=RiskKillSwitchClearState(
                clear=True,
                observed_at=NOW - timedelta(seconds=5, milliseconds=1),
            ),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_KILL_SWITCH_STATE_STALE_REASON
    assert result.observed_value == Decimal("5001")
    assert result.limit_value == Decimal("5000")
    assert result.unit == "milliseconds"


async def test_kill_switch_clear_rule_rejects_future_state() -> None:
    result = await KillSwitchClearRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            kill_switch_clear=RiskKillSwitchClearState(
                clear=True,
                observed_at=NOW + timedelta(milliseconds=1),
            ),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_KILL_SWITCH_STATE_FUTURE_REASON
    assert result.observed_value == Decimal("1")
    assert result.limit_value == Decimal("0")
    assert result.unit == "milliseconds"


def test_risk_context_kill_switch_clear_validates_inputs() -> None:
    context = RiskContext(
        evaluated_at=NOW,
        kill_switch_clear=RiskKillSwitchClearState(
            clear=False,
            active_scopes=(KillSwitchScope.GLOBAL,),
            observed_at=NOW,
        ),
    )
    state = context.kill_switch_clear_state()

    assert state == context.kill_switch_clear
    assert state is not None
    assert state.active_scopes == frozenset({KillSwitchScope.GLOBAL})
    with pytest.raises(FrozenInstanceError):
        context.kill_switch_clear = RiskKillSwitchClearState(clear=True, observed_at=NOW)
    with pytest.raises(RiskConfigurationError, match="RiskKillSwitchClearState"):
        RiskContext(evaluated_at=NOW, kill_switch_clear=True)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="clear"):
        RiskKillSwitchClearState(
            clear=1,  # type: ignore[arg-type]
            observed_at=NOW,
        )
    with pytest.raises(TypeError, match="active_scopes"):
        RiskKillSwitchClearState(
            clear=False,
            active_scopes="global",  # type: ignore[arg-type]
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="KillSwitchScope"):
        RiskKillSwitchClearState(
            clear=False,
            active_scopes={"global"},  # type: ignore[arg-type]
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="clear kill switch"):
        RiskKillSwitchClearState(
            clear=True,
            active_scopes={KillSwitchScope.GLOBAL},
            observed_at=NOW,
        )


async def test_kill_switch_clear_rule_rejects_invalid_configuration_and_inputs() -> None:
    rule = KillSwitchClearRule(max_state_age=timedelta(seconds=5))

    with pytest.raises(RiskConfigurationError, match="max_state_age"):
        KillSwitchClearRule(max_state_age=timedelta(0))
    with pytest.raises(TypeError, match="max_state_age"):
        KillSwitchClearRule(max_state_age=5)  # type: ignore[arg-type]
    with pytest.raises(RiskInputError, match="OrderIntent"):
        await rule.evaluate(object(), RiskContext(evaluated_at=NOW))  # type: ignore[arg-type]
    with pytest.raises(RiskInputError, match="RiskContext"):
        await rule.evaluate(_intent(), object())  # type: ignore[arg-type]


def _intent() -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_risk_kill_switch_clear",
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
            "correlation_id": "corr_risk_kill_switch_clear",
            "idempotency_key": "idem-risk-kill-switch-clear",
        }
    )
