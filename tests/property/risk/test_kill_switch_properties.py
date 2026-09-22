"""Property tests for the RISK-019 kill-switch clear rule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.risk import (
    RISK_KILL_SWITCH_ACTIVE_REASON,
    RISK_KILL_SWITCH_CLEAR_REASON,
    RISK_KILL_SWITCH_NOT_CLEAR_REASON,
    RISK_KILL_SWITCH_STATE_FUTURE_REASON,
    RISK_KILL_SWITCH_STATE_STALE_REASON,
    KillSwitchClearRule,
    RiskContext,
    RiskKillSwitchClearState,
)
from pmrp.schemas.enums import OrderType, Side, TimeInForce
from pmrp.schemas.identifiers import ContractId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.risk import KillSwitchScope

pytestmark = pytest.mark.property

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_risk_kill_switch_clear_property")
CONTRACT_ID = ContractId("ctr_risk_kill_switch_clear_property")
STRATEGY_ID = StrategyId("strat_risk_kill_switch_clear_property")


@given(age_ms=st.integers(min_value=0, max_value=5000))
async def test_kill_switch_clear_rule_is_deterministic_when_clear(age_ms: int) -> None:
    rule = KillSwitchClearRule(max_state_age=timedelta(milliseconds=5000))
    context = _context(
        clear=True,
        observed_at=NOW - timedelta(milliseconds=age_ms),
    )

    first = await rule.evaluate(_intent(), context)
    second = await rule.evaluate(_intent(), context)

    assert first == second
    assert first.passed is True
    assert first.reason_code == RISK_KILL_SWITCH_CLEAR_REASON
    assert first.observed_value == Decimal("1")
    assert first.limit_value == Decimal("1")


@given(
    active_scopes=st.sets(
        st.sampled_from(tuple(KillSwitchScope)),
        min_size=1,
        max_size=len(tuple(KillSwitchScope)),
    )
)
async def test_kill_switch_clear_rule_rejects_any_active_scope(
    active_scopes: set[KillSwitchScope],
) -> None:
    result = await KillSwitchClearRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(),
        _context(
            clear=False,
            active_scopes=active_scopes,
            observed_at=NOW,
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_KILL_SWITCH_ACTIVE_REASON
    assert result.observed_value == Decimal(len(active_scopes))
    assert result.limit_value == Decimal("0")


@given(age_ms=st.integers(min_value=0, max_value=5000))
async def test_kill_switch_clear_rule_rejects_any_not_clear_flag(age_ms: int) -> None:
    result = await KillSwitchClearRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(),
        _context(
            clear=False,
            observed_at=NOW - timedelta(milliseconds=age_ms),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_KILL_SWITCH_NOT_CLEAR_REASON
    assert result.observed_value == Decimal("0")
    assert result.limit_value == Decimal("1")


@given(age_ms=st.integers(min_value=5001, max_value=600000))
async def test_kill_switch_clear_rule_rejects_any_stale_state(age_ms: int) -> None:
    result = await KillSwitchClearRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(),
        _context(
            clear=True,
            observed_at=NOW - timedelta(milliseconds=age_ms),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_KILL_SWITCH_STATE_STALE_REASON
    assert result.observed_value == Decimal(age_ms)
    assert result.limit_value == Decimal("5000")


@given(future_ms=st.integers(min_value=1, max_value=600000))
async def test_kill_switch_clear_rule_rejects_any_future_state(future_ms: int) -> None:
    result = await KillSwitchClearRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(),
        _context(
            clear=True,
            observed_at=NOW + timedelta(milliseconds=future_ms),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_KILL_SWITCH_STATE_FUTURE_REASON
    assert result.observed_value == Decimal(future_ms)
    assert result.limit_value == Decimal("0")


def _context(
    *,
    clear: bool,
    observed_at: datetime,
    active_scopes: set[KillSwitchScope] | None = None,
) -> RiskContext:
    return RiskContext(
        evaluated_at=NOW,
        kill_switch_clear=RiskKillSwitchClearState(
            clear=clear,
            active_scopes=active_scopes or frozenset(),
            observed_at=observed_at,
        ),
    )


def _intent() -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_risk_kill_switch_clear_property",
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
            "correlation_id": "corr_risk_kill_switch_clear_property",
            "idempotency_key": "idem-risk-kill-switch-clear-property",
        }
    )
