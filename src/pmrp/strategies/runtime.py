"""In-process strategy runtime for canonical event processing."""

from __future__ import annotations

import asyncio
import re
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime

from pmrp.bus.protocol import EventSubscription
from pmrp.clock import Clock
from pmrp.schemas.enums import HealthStatus, StrategyState
from pmrp.schemas.events import EventEnvelope
from pmrp.schemas.identifiers import StrategyId
from pmrp.strategies.context import StrategyContext
from pmrp.strategies.errors import StrategyRuntimeError
from pmrp.strategies.health import StrategyRuntimeHealth
from pmrp.strategies.lifecycle import TERMINAL_STRATEGY_STATES, transition_strategy_state
from pmrp.strategies.protocol import Strategy

_DOTTED_EVENT_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")


class StrategyRuntime:
    """Coordinate isolated strategy event consumers in the modular monolith."""

    def __init__(
        self,
        *,
        clock: Clock,
        queue_size: int = 1024,
    ) -> None:
        if not isinstance(clock, Clock):
            msg = "clock must implement the Clock protocol"
            raise TypeError(msg)
        if type(queue_size) is not int:
            msg = "queue_size must be an int"
            raise TypeError(msg)
        if queue_size < 1:
            msg = "queue_size must be positive"
            raise ValueError(msg)
        self._clock = clock
        self._queue_size = queue_size
        self._handles: dict[StrategyId, _StrategyHandle] = {}
        self._started = False

    def register(
        self,
        strategy: Strategy,
        context: StrategyContext,
        *,
        queue_size: int | None = None,
    ) -> StrategyRuntimeHealth:
        """Register a strategy instance before runtime startup."""

        if self._started:
            raise StrategyRuntimeError(
                "Strategy registration is closed after runtime startup",
                reason_code="strategy_runtime_registration_closed",
            )
        _validate_strategy(strategy)
        if strategy.strategy_id != context.strategy_id:
            raise StrategyRuntimeError(
                "Strategy context strategy_id must match the strategy instance",
                reason_code="strategy_runtime_context_strategy_id_mismatch",
                context={
                    "strategy_id": str(strategy.strategy_id),
                    "context_strategy_id": str(context.strategy_id),
                },
            )
        if strategy.strategy_id in self._handles:
            raise StrategyRuntimeError(
                "Strategy is already registered",
                reason_code="strategy_runtime_duplicate_registration",
                context={"strategy_id": str(strategy.strategy_id)},
            )
        effective_queue_size = self._queue_size if queue_size is None else queue_size
        if type(effective_queue_size) is not int:
            msg = "strategy queue_size must be an int"
            raise TypeError(msg)
        if effective_queue_size < 1:
            msg = "strategy queue_size must be positive"
            raise ValueError(msg)

        handle = _StrategyHandle(
            strategy=strategy,
            context=context,
            subscribed_event_types=tuple(strategy.subscribed_event_types),
            queue_size=effective_queue_size,
        )
        self._handles[strategy.strategy_id] = handle
        return handle.health()

    async def start(self) -> None:
        """Initialize registered strategies and start their event consumers."""

        if self._started:
            return
        self._started = True
        await asyncio.gather(
            *(self._start_strategy(handle) for handle in self._ordered_handles()),
        )

    async def stop(self, reason: str = "runtime_stop") -> None:
        """Stop all managed strategies and close their event subscriptions."""

        self._started = False
        await asyncio.gather(
            *(self._stop_strategy(handle, reason=reason) for handle in self._ordered_handles()),
        )

    def health(self) -> tuple[StrategyRuntimeHealth, ...]:
        """Return deterministic health snapshots for all managed strategies."""

        return tuple(handle.health() for handle in self._ordered_handles())

    def strategy_health(self, strategy_id: StrategyId) -> StrategyRuntimeHealth:
        """Return health for one managed strategy."""

        try:
            return self._handles[strategy_id].health()
        except KeyError:
            raise StrategyRuntimeError(
                "Strategy is not registered",
                reason_code="strategy_runtime_strategy_not_registered",
                context={"strategy_id": str(strategy_id)},
            ) from None

    async def _start_strategy(self, handle: _StrategyHandle) -> None:
        if handle.state in TERMINAL_STRATEGY_STATES or handle.state is StrategyState.RUNNING:
            return
        handle.transition_to(StrategyState.INITIALIZING)
        initialized = await _try_initialize_strategy(handle.strategy, handle.context)
        if not initialized:
            handle.mark_start_failure(self._clock.now(), message="strategy initialization failed")
            return

        subscription = _try_subscribe_strategy(handle)
        if subscription is None:
            handle.mark_start_failure(self._clock.now(), message="strategy subscription failed")
            return

        handle.subscription = subscription
        handle.started_at = self._clock.now()
        handle.transition_to(StrategyState.RUNNING)
        handle.health_status = HealthStatus.HEALTHY
        handle.health_message = None
        handle.task = asyncio.create_task(
            self._consume_strategy_events(handle),
            name=f"pmrp-strategy-{handle.strategy.strategy_id}",
        )

    async def _consume_strategy_events(self, handle: _StrategyHandle) -> None:
        subscription = handle.subscription
        if subscription is None:
            return
        async for event in subscription:
            if handle.state is not StrategyState.RUNNING:
                break
            if event.event_type not in handle.subscribed_event_types:
                handle.ignored_events += 1
                continue
            processed = await _try_process_strategy_event(handle.strategy, event)
            handle.last_event_at = self._clock.now()
            if not processed:
                await self._degrade_strategy(handle, message="strategy event processing failed")
                break
            handle.processed_events += 1

    async def _degrade_strategy(self, handle: _StrategyHandle, *, message: str) -> None:
        handle.context.disable_order_intents()
        handle.failed_events += 1
        handle.last_failure_at = self._clock.now()
        handle.transition_to(StrategyState.DEGRADED)
        handle.health_status = HealthStatus.DEGRADED
        handle.health_message = message
        await _close_subscription(handle.subscription)

    async def _stop_strategy(self, handle: _StrategyHandle, *, reason: str) -> None:
        if handle.state in TERMINAL_STRATEGY_STATES:
            return
        if handle.state in {StrategyState.RUNNING, StrategyState.DEGRADED}:
            handle.transition_to(StrategyState.DRAINING)
        await _close_subscription(handle.subscription)
        if handle.task is not None and handle.task is not asyncio.current_task():
            with suppress(asyncio.CancelledError):
                await handle.task
        shutdown = await _try_shutdown_strategy(handle.strategy, reason)
        handle.stopped_at = self._clock.now()
        if shutdown:
            handle.transition_to(StrategyState.STOPPED)
            handle.health_status = HealthStatus.UNKNOWN
            handle.health_message = None
            return
        handle.transition_to(StrategyState.FAILED)
        handle.health_status = HealthStatus.UNHEALTHY
        handle.health_message = "strategy shutdown failed"

    def _ordered_handles(self) -> tuple[_StrategyHandle, ...]:
        return tuple(self._handles[strategy_id] for strategy_id in sorted(self._handles, key=str))


@dataclass(slots=True)
class _StrategyHandle:
    strategy: Strategy
    context: StrategyContext
    subscribed_event_types: tuple[str, ...]
    queue_size: int
    state: StrategyState = StrategyState.CREATED
    health_status: HealthStatus = HealthStatus.UNKNOWN
    health_message: str | None = None
    subscription: EventSubscription[EventEnvelope] | None = None
    task: asyncio.Task[None] | None = None
    processed_events: int = 0
    ignored_events: int = 0
    failed_events: int = 0
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    last_event_at: datetime | None = None
    last_failure_at: datetime | None = None

    def transition_to(self, next_state: StrategyState) -> None:
        self.state = transition_strategy_state(self.state, next_state)

    def mark_start_failure(self, occurred_at: datetime, *, message: str) -> None:
        self.context.disable_order_intents()
        self.failed_events += 1
        self.last_failure_at = occurred_at
        self.transition_to(StrategyState.FAILED)
        self.health_status = HealthStatus.UNHEALTHY
        self.health_message = message

    def health(self) -> StrategyRuntimeHealth:
        return StrategyRuntimeHealth(
            strategy_id=self.strategy.strategy_id,
            state=self.state,
            health_status=self.health_status,
            health_message=self.health_message,
            subscribed_event_types=self.subscribed_event_types,
            processed_events=self.processed_events,
            ignored_events=self.ignored_events,
            failed_events=self.failed_events,
            started_at=self.started_at,
            stopped_at=self.stopped_at,
            last_event_at=self.last_event_at,
            last_failure_at=self.last_failure_at,
        )


async def _try_initialize_strategy(strategy: Strategy, context: StrategyContext) -> bool:
    try:
        await strategy.initialize(context)
    except Exception:
        return False
    return True


def _try_subscribe_strategy(handle: _StrategyHandle) -> EventSubscription[EventEnvelope] | None:
    try:
        return handle.context.subscribe(
            EventEnvelope,
            consumer_name=f"strategy:{handle.strategy.strategy_id}",
            queue_size=handle.queue_size,
        )
    except Exception:
        return None


async def _try_process_strategy_event(strategy: Strategy, event: EventEnvelope) -> bool:
    try:
        await strategy.on_event(event)
    except Exception:
        return False
    return True


async def _try_shutdown_strategy(strategy: Strategy, reason: str) -> bool:
    try:
        await strategy.shutdown(reason)
    except Exception:
        return False
    return True


async def _close_subscription(subscription: EventSubscription[EventEnvelope] | None) -> None:
    if subscription is None:
        return
    try:
        await subscription.close()
    except Exception:
        return


def _validate_strategy(strategy: Strategy) -> None:
    if not isinstance(strategy, Strategy):
        raise StrategyRuntimeError(
            "Strategy instance does not satisfy the strategy protocol",
            reason_code="strategy_runtime_protocol_invalid",
        )
    if not isinstance(strategy.strategy_id, StrategyId):
        raise StrategyRuntimeError(
            "Strategy strategy_id must be a StrategyId",
            reason_code="strategy_runtime_strategy_id_invalid",
        )
    _validate_required_text(strategy.strategy_type, field_name="strategy_type")
    _validate_required_text(strategy.strategy_version, field_name="strategy_version")
    if type(strategy.configuration_schema_version) is not int:
        msg = "configuration_schema_version must be an int"
        raise TypeError(msg)
    if strategy.configuration_schema_version < 1:
        msg = "configuration_schema_version must be positive"
        raise ValueError(msg)
    if not strategy.subscribed_event_types:
        raise StrategyRuntimeError(
            "Strategy must subscribe to at least one event type",
            reason_code="strategy_runtime_subscriptions_empty",
            context={"strategy_id": str(strategy.strategy_id)},
        )
    for event_type in strategy.subscribed_event_types:
        _validate_event_type(event_type)


def _validate_required_text(value: str, *, field_name: str) -> None:
    if type(value) is not str:
        msg = f"{field_name} must be a string"
        raise TypeError(msg)
    if value == "" or value.strip() != value:
        msg = f"{field_name} must be nonempty without surrounding whitespace"
        raise ValueError(msg)


def _validate_event_type(value: str) -> None:
    if type(value) is not str:
        msg = "subscribed_event_types must contain strings"
        raise TypeError(msg)
    if _DOTTED_EVENT_TYPE_PATTERN.fullmatch(value) is None:
        msg = "subscribed_event_types must use dotted lowercase event types"
        raise ValueError(msg)
