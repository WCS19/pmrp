"""Unit tests for deriving RISK-019 context from canonical kill switches."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pmrp.risk import (
    KillSwitchClearStateFactory,
    KillSwitchEvaluationSubject,
    RiskConfigurationError,
    RiskContext,
    RiskInputError,
    build_kill_switch_clear_state,
)
from pmrp.schemas.enums import OrderType, Side, TimeInForce
from pmrp.schemas.identifiers import AccountId, ContractId, ExchangeId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.risk import KillSwitchScope, KillSwitchState

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
STRATEGY_ID = StrategyId("strat_kill_switch_subject")
OTHER_STRATEGY_ID = StrategyId("strat_kill_switch_other")
MARKET_ID = MarketId("mkt_kill_switch_subject")
OTHER_MARKET_ID = MarketId("mkt_kill_switch_other")
CONTRACT_ID = ContractId("ctr_kill_switch_subject")
EXCHANGE_ID = ExchangeId("xchg_kalshi")
ACCOUNT_ID = AccountId("acct_kill_switch_subject")
EXECUTION_GATEWAY_ID = "gateway-primary"


def test_clear_state_factory_returns_clear_when_no_active_switch_matches() -> None:
    subject = KillSwitchEvaluationSubject(strategy_id=STRATEGY_ID, market_id=MARKET_ID)
    state = build_kill_switch_clear_state(
        (
            _kill_switch(
                "inactive_strategy",
                scope=KillSwitchScope.STRATEGY,
                scope_id=str(STRATEGY_ID),
                active=False,
            ),
            _kill_switch(
                "active_other_strategy",
                scope=KillSwitchScope.STRATEGY,
                scope_id=str(OTHER_STRATEGY_ID),
            ),
            _kill_switch(
                "active_other_market",
                scope=KillSwitchScope.MARKET,
                scope_id=str(OTHER_MARKET_ID),
            ),
        ),
        subject,
        observed_at=NOW,
    )

    assert state.clear is True
    assert state.observed_at == NOW
    assert state.active_scopes == frozenset()


def test_clear_state_factory_matches_all_supported_subject_scopes() -> None:
    subject = KillSwitchEvaluationSubject(
        strategy_id=STRATEGY_ID,
        market_id=MARKET_ID,
        exchange_id=EXCHANGE_ID,
        account_id=ACCOUNT_ID,
        execution_gateway_id=EXECUTION_GATEWAY_ID,
    )

    state = KillSwitchClearStateFactory().clear_state_for_subject(
        (
            _kill_switch("global", scope=KillSwitchScope.GLOBAL),
            _kill_switch(
                "strategy",
                scope=KillSwitchScope.STRATEGY,
                scope_id=str(STRATEGY_ID),
            ),
            _kill_switch("market", scope=KillSwitchScope.MARKET, scope_id=str(MARKET_ID)),
            _kill_switch(
                "exchange",
                scope=KillSwitchScope.EXCHANGE,
                scope_id=str(EXCHANGE_ID),
            ),
            _kill_switch("account", scope=KillSwitchScope.ACCOUNT, scope_id=str(ACCOUNT_ID)),
            _kill_switch(
                "gateway",
                scope=KillSwitchScope.EXECUTION_GATEWAY,
                scope_id=EXECUTION_GATEWAY_ID,
            ),
            _kill_switch(
                "unmatched_market",
                scope=KillSwitchScope.MARKET,
                scope_id=str(OTHER_MARKET_ID),
            ),
        ),
        subject,
        observed_at=NOW,
    )

    assert state.clear is False
    assert state.active_scopes == frozenset(
        {
            KillSwitchScope.GLOBAL,
            KillSwitchScope.STRATEGY,
            KillSwitchScope.MARKET,
            KillSwitchScope.EXCHANGE,
            KillSwitchScope.ACCOUNT,
            KillSwitchScope.EXECUTION_GATEWAY,
        }
    )


def test_clear_state_factory_does_not_match_missing_optional_subject_identifiers() -> None:
    subject = KillSwitchEvaluationSubject(strategy_id=STRATEGY_ID, market_id=MARKET_ID)

    state = build_kill_switch_clear_state(
        (
            _kill_switch(
                "exchange",
                scope=KillSwitchScope.EXCHANGE,
                scope_id=str(EXCHANGE_ID),
            ),
            _kill_switch("account", scope=KillSwitchScope.ACCOUNT, scope_id=str(ACCOUNT_ID)),
            _kill_switch(
                "gateway",
                scope=KillSwitchScope.EXECUTION_GATEWAY,
                scope_id=EXECUTION_GATEWAY_ID,
            ),
        ),
        subject,
        observed_at=NOW,
    )

    assert state.clear is True
    assert state.active_scopes == frozenset()


def test_evaluation_subject_from_intent_uses_context_market_exchange_mapping() -> None:
    intent = _intent()
    context = RiskContext(evaluated_at=NOW, market_exchanges={MARKET_ID: EXCHANGE_ID})

    subject = KillSwitchEvaluationSubject.from_intent(
        intent,
        context,
        account_id=ACCOUNT_ID,
        execution_gateway_id=EXECUTION_GATEWAY_ID,
    )

    assert subject.strategy_id == STRATEGY_ID
    assert subject.market_id == MARKET_ID
    assert subject.exchange_id == EXCHANGE_ID
    assert subject.account_id == ACCOUNT_ID
    assert subject.execution_gateway_id == EXECUTION_GATEWAY_ID


def test_clear_state_factory_is_deterministic_for_same_inputs() -> None:
    subject = KillSwitchEvaluationSubject(strategy_id=STRATEGY_ID, market_id=MARKET_ID)
    kill_switches = (
        _kill_switch("global", scope=KillSwitchScope.GLOBAL),
        _kill_switch("market", scope=KillSwitchScope.MARKET, scope_id=str(MARKET_ID)),
    )

    first = build_kill_switch_clear_state(kill_switches, subject, observed_at=NOW)
    second = build_kill_switch_clear_state(kill_switches, subject, observed_at=NOW)

    assert first == second


def test_clear_state_factory_validates_inputs() -> None:
    subject = KillSwitchEvaluationSubject(strategy_id=STRATEGY_ID, market_id=MARKET_ID)

    with pytest.raises(RiskConfigurationError, match="StrategyId"):
        KillSwitchEvaluationSubject(  # type: ignore[arg-type]
            strategy_id=str(STRATEGY_ID),
            market_id=MARKET_ID,
        )
    with pytest.raises(TypeError, match="execution_gateway_id"):
        KillSwitchEvaluationSubject(  # type: ignore[arg-type]
            strategy_id=STRATEGY_ID,
            market_id=MARKET_ID,
            execution_gateway_id=1,
        )
    with pytest.raises(RiskConfigurationError, match="execution_gateway_id"):
        KillSwitchEvaluationSubject(
            strategy_id=STRATEGY_ID,
            market_id=MARKET_ID,
            execution_gateway_id="",
        )
    with pytest.raises(TypeError, match="kill_switches"):
        build_kill_switch_clear_state("not-a-sequence", subject, observed_at=NOW)  # type: ignore[arg-type]
    with pytest.raises(RiskInputError, match="KillSwitchState"):
        build_kill_switch_clear_state((object(),), subject, observed_at=NOW)  # type: ignore[arg-type]
    with pytest.raises(RiskInputError, match="KillSwitchEvaluationSubject"):
        build_kill_switch_clear_state((), object(), observed_at=NOW)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="timezone-aware"):
        build_kill_switch_clear_state(
            (),
            subject,
            observed_at=NOW.replace(tzinfo=None),
        )
    with pytest.raises(RiskConfigurationError, match="scope_id"):
        build_kill_switch_clear_state(
            (_kill_switch("missing_scope", scope=KillSwitchScope.STRATEGY),),
            subject,
            observed_at=NOW,
        )
    with pytest.raises(RiskInputError, match="OrderIntent"):
        KillSwitchEvaluationSubject.from_intent(object(), RiskContext(evaluated_at=NOW))  # type: ignore[arg-type]
    with pytest.raises(RiskInputError, match="RiskContext"):
        KillSwitchEvaluationSubject.from_intent(_intent(), object())  # type: ignore[arg-type]


def _kill_switch(
    suffix: str,
    *,
    scope: KillSwitchScope,
    scope_id: str | None = None,
    active: bool = True,
) -> KillSwitchState:
    payload: dict[str, object] = {
        "kill_switch_id": f"kill_{suffix}",
        "scope": scope,
        "scope_id": scope_id,
        "active": active,
        "version": 0,
    }
    if active:
        payload.update(
            {
                "activated_at": NOW - timedelta(seconds=1),
                "activated_by": "operator",
                "activation_reason": "test kill switch",
            }
        )
    else:
        payload.update(
            {
                "activated_at": NOW - timedelta(minutes=1),
                "activated_by": "operator",
                "activation_reason": "test kill switch",
                "released_at": NOW,
                "released_by": "operator",
                "release_reason": "test release",
            }
        )
    return KillSwitchState.model_validate(payload)


def _intent() -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_kill_switch_subject",
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
            "correlation_id": "corr_kill_switch_subject",
            "idempotency_key": "idem-kill-switch-subject",
        }
    )
