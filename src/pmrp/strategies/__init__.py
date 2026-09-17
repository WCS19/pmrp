"""Strategy interfaces and context primitives."""

from pmrp.strategies.context import (
    APPROVED_STRATEGY_CONTEXT_SERVICES,
    FORBIDDEN_STRATEGY_CONTEXT_SERVICES,
    StrategyContext,
    StrategyLogger,
    StrategyMetrics,
    StrategyOrderIntentPublisher,
    StrategySignalPublisher,
)
from pmrp.strategies.errors import (
    StrategyContextError,
    StrategyEmissionError,
    StrategyError,
    StrategyLifecycleError,
    StrategyProtocolError,
    StrategyRegistryError,
    StrategyRuntimeError,
    StrategyStateStoreError,
)
from pmrp.strategies.health import StrategyRuntimeHealth
from pmrp.strategies.lifecycle import (
    ALLOWED_STRATEGY_STATE_TRANSITIONS,
    TERMINAL_STRATEGY_STATES,
    transition_strategy_state,
    validate_strategy_state_transition,
)
from pmrp.strategies.protocol import Strategy, StrategyFactory
from pmrp.strategies.registry import (
    StrategyConfigurationModel,
    StrategyRegistry,
    StrategyTypeRegistration,
    UnknownStrategyTypeError,
)
from pmrp.strategies.runtime import (
    StrategyLifecycleEvent,
    StrategyLifecycleEventPublisher,
    StrategyRuntime,
)
from pmrp.strategies.state_store import (
    InMemoryStrategyStateStore,
    StrategyStateCheckpoint,
    StrategyStateStore,
    thaw_checkpoint_state,
)

__all__ = [
    "ALLOWED_STRATEGY_STATE_TRANSITIONS",
    "APPROVED_STRATEGY_CONTEXT_SERVICES",
    "FORBIDDEN_STRATEGY_CONTEXT_SERVICES",
    "TERMINAL_STRATEGY_STATES",
    "InMemoryStrategyStateStore",
    "Strategy",
    "StrategyConfigurationModel",
    "StrategyContext",
    "StrategyContextError",
    "StrategyEmissionError",
    "StrategyError",
    "StrategyFactory",
    "StrategyLifecycleError",
    "StrategyLifecycleEvent",
    "StrategyLifecycleEventPublisher",
    "StrategyLogger",
    "StrategyMetrics",
    "StrategyOrderIntentPublisher",
    "StrategyProtocolError",
    "StrategyRegistry",
    "StrategyRegistryError",
    "StrategyRuntime",
    "StrategyRuntimeError",
    "StrategyRuntimeHealth",
    "StrategySignalPublisher",
    "StrategyStateCheckpoint",
    "StrategyStateStore",
    "StrategyStateStoreError",
    "StrategyTypeRegistration",
    "UnknownStrategyTypeError",
    "thaw_checkpoint_state",
    "transition_strategy_state",
    "validate_strategy_state_transition",
]
