"""Strategy lifecycle primitive tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pmrp.schemas.enums import HealthStatus, StrategyState
from pmrp.schemas.identifiers import StrategyId
from pmrp.strategies import (
    ALLOWED_STRATEGY_STATE_TRANSITIONS,
    TERMINAL_STRATEGY_STATES,
    StrategyLifecycleError,
    StrategyRuntimeHealth,
    transition_strategy_state,
    validate_strategy_state_transition,
)

pytestmark = pytest.mark.unit


def test_strategy_lifecycle_allows_documented_startup_path() -> None:
    state = StrategyState.CREATED

    state = transition_strategy_state(state, StrategyState.INITIALIZING)
    state = transition_strategy_state(state, StrategyState.RUNNING)
    state = transition_strategy_state(state, StrategyState.DRAINING)
    state = transition_strategy_state(state, StrategyState.STOPPED)

    assert state is StrategyState.STOPPED


def test_strategy_lifecycle_allows_running_failure_path() -> None:
    state = transition_strategy_state(StrategyState.RUNNING, StrategyState.DEGRADED)

    assert transition_strategy_state(state, StrategyState.STOPPED) is StrategyState.STOPPED


def test_strategy_lifecycle_rejects_invalid_transition() -> None:
    with pytest.raises(StrategyLifecycleError) as exc_info:
        validate_strategy_state_transition(StrategyState.STOPPED, StrategyState.RUNNING)

    assert str(exc_info.value) == "Strategy lifecycle transition is not allowed"
    assert exc_info.value.reason_code == "strategy_lifecycle_transition_invalid"
    assert exc_info.value.context["previous_state"] == "stopped"
    assert exc_info.value.context["next_state"] == "running"


def test_strategy_terminal_states_have_no_outbound_transitions() -> None:
    assert frozenset({StrategyState.STOPPED, StrategyState.FAILED}) == TERMINAL_STRATEGY_STATES
    for state in TERMINAL_STRATEGY_STATES:
        assert ALLOWED_STRATEGY_STATE_TRANSITIONS[state] == frozenset()


def test_strategy_runtime_health_accepts_valid_snapshot_and_normalizes_time() -> None:
    health = StrategyRuntimeHealth(
        strategy_id=StrategyId("strat_health_test_v1"),
        state=StrategyState.RUNNING,
        health_status=HealthStatus.HEALTHY,
        health_message=None,
        subscribed_event_types=("market.snapshot",),
        processed_events=2,
        ignored_events=1,
        failed_events=0,
        started_at=datetime(2026, 7, 27, 15, 0, tzinfo=UTC),
    )

    assert health.strategy_id == "strat_health_test_v1"
    assert health.state is StrategyState.RUNNING
    assert health.started_at == datetime(2026, 7, 27, 15, 0, tzinfo=UTC)


def test_strategy_runtime_health_rejects_invalid_counts_and_times() -> None:
    with pytest.raises(ValueError, match="failed_events must not be negative"):
        StrategyRuntimeHealth(
            strategy_id=StrategyId("strat_health_test_v1"),
            state=StrategyState.RUNNING,
            health_status=HealthStatus.HEALTHY,
            health_message=None,
            subscribed_event_types=("market.snapshot",),
            processed_events=0,
            ignored_events=0,
            failed_events=-1,
        )

    with pytest.raises(ValueError, match="timezone-aware"):
        StrategyRuntimeHealth(
            strategy_id=StrategyId("strat_health_test_v1"),
            state=StrategyState.RUNNING,
            health_status=HealthStatus.HEALTHY,
            health_message=None,
            subscribed_event_types=("market.snapshot",),
            processed_events=0,
            ignored_events=0,
            failed_events=0,
            started_at=datetime.fromisoformat("2026-07-27T15:00:00"),
        )
