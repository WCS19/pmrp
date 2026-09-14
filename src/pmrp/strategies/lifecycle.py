"""Strategy lifecycle transition validation."""

from __future__ import annotations

from pmrp.schemas.enums import StrategyState
from pmrp.strategies.errors import StrategyLifecycleError

TERMINAL_STRATEGY_STATES = frozenset({StrategyState.STOPPED, StrategyState.FAILED})

ALLOWED_STRATEGY_STATE_TRANSITIONS: dict[StrategyState, frozenset[StrategyState]] = {
    StrategyState.CREATED: frozenset(
        {
            StrategyState.INITIALIZING,
            StrategyState.STOPPED,
            StrategyState.FAILED,
        }
    ),
    StrategyState.INITIALIZING: frozenset(
        {
            StrategyState.RUNNING,
            StrategyState.DEGRADED,
            StrategyState.STOPPED,
            StrategyState.FAILED,
        }
    ),
    StrategyState.RUNNING: frozenset(
        {
            StrategyState.DEGRADED,
            StrategyState.DRAINING,
            StrategyState.STOPPED,
            StrategyState.FAILED,
        }
    ),
    StrategyState.DEGRADED: frozenset(
        {
            StrategyState.DRAINING,
            StrategyState.STOPPED,
            StrategyState.FAILED,
        }
    ),
    StrategyState.DRAINING: frozenset(
        {
            StrategyState.STOPPED,
            StrategyState.FAILED,
        }
    ),
    StrategyState.STOPPED: frozenset(),
    StrategyState.FAILED: frozenset(),
}


def validate_strategy_state_transition(
    previous_state: StrategyState,
    next_state: StrategyState,
) -> None:
    """Reject impossible strategy lifecycle transitions."""

    if previous_state is next_state:
        return
    if next_state not in ALLOWED_STRATEGY_STATE_TRANSITIONS[previous_state]:
        raise StrategyLifecycleError(
            "Strategy lifecycle transition is not allowed",
            reason_code="strategy_lifecycle_transition_invalid",
            context={
                "previous_state": previous_state.value,
                "next_state": next_state.value,
            },
        )


def transition_strategy_state(
    previous_state: StrategyState,
    next_state: StrategyState,
) -> StrategyState:
    """Return a validated next strategy state."""

    validate_strategy_state_transition(previous_state, next_state)
    return next_state
