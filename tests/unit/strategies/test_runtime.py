"""Strategy runtime foundation tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from pmrp.bus import InProcessEventBus
from pmrp.clock import FrozenClock
from pmrp.schemas.enums import HealthStatus, Side, StrategyState
from pmrp.schemas.events import EventEnvelope
from pmrp.schemas.identifiers import SignalId, StrategyId
from pmrp.schemas.orders import OrderIntent
from pmrp.strategies import (
    StrategyContext,
    StrategyEmissionError,
    StrategyRuntime,
    StrategyRuntimeError,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 7, 27, 15, 0, tzinfo=UTC)


def test_strategy_runtime_registers_strategy_with_created_health() -> None:
    event_bus = InProcessEventBus()
    runtime = StrategyRuntime(clock=FrozenClock(NOW))
    strategy = RecordingStrategy(strategy_id=StrategyId("strat_runtime_a_v1"))

    health = runtime.register(strategy, _context(strategy.strategy_id, event_bus=event_bus))

    assert health.strategy_id == strategy.strategy_id
    assert health.state is StrategyState.CREATED
    assert health.health_status is HealthStatus.UNKNOWN
    assert health.subscribed_event_types == ("market.snapshot",)
    assert health.processed_events == 0
    assert runtime.strategy_health(strategy.strategy_id) == health


async def test_strategy_runtime_processes_matching_events_sequentially() -> None:
    event_bus = InProcessEventBus(deterministic=True)
    runtime = StrategyRuntime(clock=FrozenClock(NOW), queue_size=4)
    strategy = RecordingStrategy(strategy_id=StrategyId("strat_runtime_order_v1"))
    runtime.register(strategy, _context(strategy.strategy_id, event_bus=event_bus))

    await runtime.start()
    await event_bus.publish(_event("evt_strategy_runtime_ignored", "market.delta"))
    await event_bus.publish(_event("evt_strategy_runtime_0001", "market.snapshot"))
    await event_bus.publish(_event("evt_strategy_runtime_0002", "market.snapshot"))
    await _wait_until(lambda: len(strategy.events) == 2)

    health = runtime.strategy_health(strategy.strategy_id)
    assert [event.event_id for event in strategy.events] == [
        "evt_strategy_runtime_0001",
        "evt_strategy_runtime_0002",
    ]
    assert health.state is StrategyState.RUNNING
    assert health.health_status is HealthStatus.HEALTHY
    assert health.processed_events == 2
    assert health.ignored_events == 1
    assert health.failed_events == 0
    assert health.started_at == NOW
    assert health.last_event_at == NOW

    await runtime.stop("test_complete")
    assert strategy.shutdown_reason == "test_complete"
    assert runtime.strategy_health(strategy.strategy_id).state is StrategyState.STOPPED


async def test_strategy_runtime_isolates_event_processing_failure() -> None:
    event_bus = InProcessEventBus(deterministic=True)
    runtime = StrategyRuntime(clock=FrozenClock(NOW), queue_size=4)
    good_strategy = RecordingStrategy(strategy_id=StrategyId("strat_runtime_good_v1"))
    failing_strategy = RecordingStrategy(
        strategy_id=StrategyId("strat_runtime_failing_v1"),
        fail_on_event_type="market.snapshot",
    )
    good_intents = RecordingOrderIntentPublisher()
    failing_intents = RecordingOrderIntentPublisher()
    good_context = _context(
        good_strategy.strategy_id,
        event_bus=event_bus,
        order_intent_publisher=good_intents,
    )
    failing_context = _context(
        failing_strategy.strategy_id,
        event_bus=event_bus,
        order_intent_publisher=failing_intents,
    )
    runtime.register(good_strategy, good_context)
    runtime.register(failing_strategy, failing_context)

    await runtime.start()
    await event_bus.publish(_event("evt_strategy_runtime_failure", "market.snapshot"))
    await _wait_until(lambda: len(good_strategy.events) == 1)
    await _wait_until(
        lambda: runtime.strategy_health(failing_strategy.strategy_id).failed_events == 1
    )

    good_health = runtime.strategy_health(good_strategy.strategy_id)
    failing_health = runtime.strategy_health(failing_strategy.strategy_id)
    assert good_health.state is StrategyState.RUNNING
    assert good_health.health_status is HealthStatus.HEALTHY
    assert good_health.processed_events == 1
    assert failing_health.state is StrategyState.DEGRADED
    assert failing_health.health_status is HealthStatus.DEGRADED
    assert failing_health.health_message == "strategy event processing failed"
    assert failing_health.processed_events == 0
    assert failing_health.failed_events == 1
    assert failing_context.order_intents_enabled is False

    with pytest.raises(StrategyEmissionError, match="disabled"):
        await failing_context.publish_order_intent(_order_intent(failing_strategy.strategy_id))

    await good_context.publish_order_intent(_order_intent(good_strategy.strategy_id))
    assert len(good_intents.intents) == 1
    assert failing_intents.intents == []

    await runtime.stop("test_complete")
    assert runtime.strategy_health(good_strategy.strategy_id).state is StrategyState.STOPPED
    assert runtime.strategy_health(failing_strategy.strategy_id).state is StrategyState.STOPPED


async def test_strategy_runtime_isolates_initialization_failure() -> None:
    event_bus = InProcessEventBus(deterministic=True)
    runtime = StrategyRuntime(clock=FrozenClock(NOW))
    good_strategy = RecordingStrategy(strategy_id=StrategyId("strat_runtime_init_good_v1"))
    failing_strategy = RecordingStrategy(
        strategy_id=StrategyId("strat_runtime_init_bad_v1"),
        fail_initialize=True,
    )
    failing_context = _context(failing_strategy.strategy_id, event_bus=event_bus)
    runtime.register(good_strategy, _context(good_strategy.strategy_id, event_bus=event_bus))
    runtime.register(failing_strategy, failing_context)

    await runtime.start()

    good_health = runtime.strategy_health(good_strategy.strategy_id)
    failing_health = runtime.strategy_health(failing_strategy.strategy_id)
    assert good_health.state is StrategyState.RUNNING
    assert good_health.health_status is HealthStatus.HEALTHY
    assert failing_health.state is StrategyState.FAILED
    assert failing_health.health_status is HealthStatus.UNHEALTHY
    assert failing_health.health_message == "strategy initialization failed"
    assert failing_health.failed_events == 1
    assert failing_context.order_intents_enabled is False

    await runtime.stop("test_complete")


async def test_strategy_runtime_rejects_duplicate_and_late_registration() -> None:
    event_bus = InProcessEventBus()
    runtime = StrategyRuntime(clock=FrozenClock(NOW))
    strategy = RecordingStrategy(strategy_id=StrategyId("strat_runtime_duplicate_v1"))
    runtime.register(strategy, _context(strategy.strategy_id, event_bus=event_bus))

    with pytest.raises(StrategyRuntimeError) as duplicate_error:
        runtime.register(strategy, _context(strategy.strategy_id, event_bus=event_bus))

    assert duplicate_error.value.reason_code == "strategy_runtime_duplicate_registration"

    await runtime.start()
    late_strategy = RecordingStrategy(strategy_id=StrategyId("strat_runtime_late_v1"))
    with pytest.raises(StrategyRuntimeError) as late_error:
        runtime.register(late_strategy, _context(late_strategy.strategy_id, event_bus=event_bus))

    assert late_error.value.reason_code == "strategy_runtime_registration_closed"
    await runtime.stop("test_complete")


def test_strategy_runtime_rejects_context_mismatch_and_invalid_strategy_metadata() -> None:
    event_bus = InProcessEventBus()
    runtime = StrategyRuntime(clock=FrozenClock(NOW))
    strategy = RecordingStrategy(strategy_id=StrategyId("strat_runtime_mismatch_v1"))

    with pytest.raises(StrategyRuntimeError) as mismatch_error:
        runtime.register(
            strategy,
            _context(StrategyId("strat_runtime_other_v1"), event_bus=event_bus),
        )

    assert mismatch_error.value.reason_code == "strategy_runtime_context_strategy_id_mismatch"

    empty_subscription_strategy = RecordingStrategy(
        strategy_id=StrategyId("strat_runtime_empty_v1"),
        subscribed_event_types=(),
    )
    with pytest.raises(StrategyRuntimeError) as empty_error:
        runtime.register(
            empty_subscription_strategy,
            _context(empty_subscription_strategy.strategy_id, event_bus=event_bus),
        )

    assert empty_error.value.reason_code == "strategy_runtime_subscriptions_empty"


class RecordingStrategy:
    def __init__(
        self,
        *,
        strategy_id: StrategyId,
        subscribed_event_types: tuple[str, ...] = ("market.snapshot",),
        fail_initialize: bool = False,
        fail_on_event_type: str | None = None,
    ) -> None:
        self._strategy_id = strategy_id
        self._subscribed_event_types = subscribed_event_types
        self._fail_initialize = fail_initialize
        self._fail_on_event_type = fail_on_event_type
        self.initialized_context: StrategyContext | None = None
        self.events: list[EventEnvelope] = []
        self.shutdown_reason: str | None = None

    @property
    def strategy_id(self) -> StrategyId:
        return self._strategy_id

    @property
    def strategy_type(self) -> str:
        return "recording"

    @property
    def strategy_version(self) -> str:
        return "1.0.0"

    @property
    def configuration_schema_version(self) -> int:
        return 1

    @property
    def subscribed_event_types(self) -> tuple[str, ...]:
        return self._subscribed_event_types

    async def initialize(self, context: StrategyContext) -> None:
        if self._fail_initialize:
            raise RuntimeError("raw_sensitive_payload")
        self.initialized_context = context

    async def on_event(self, event: object) -> None:
        if not isinstance(event, EventEnvelope):
            raise TypeError("event must be an EventEnvelope")
        if event.event_type == self._fail_on_event_type:
            raise RuntimeError("raw_sensitive_payload")
        self.events.append(event)

    async def shutdown(self, reason: str) -> None:
        self.shutdown_reason = reason


class RecordingSignalPublisher:
    async def publish_signal(self, signal: object) -> None:
        del signal


class RecordingOrderIntentPublisher:
    def __init__(self) -> None:
        self.intents: list[OrderIntent] = []

    async def publish_order_intent(self, intent: OrderIntent) -> None:
        self.intents.append(intent)


def _context(
    strategy_id: StrategyId,
    *,
    event_bus: InProcessEventBus,
    order_intent_publisher: RecordingOrderIntentPublisher | None = None,
) -> StrategyContext:
    return StrategyContext(
        strategy_id=strategy_id,
        clock=FrozenClock(NOW),
        event_bus=event_bus,
        signal_publisher=RecordingSignalPublisher(),
        order_intent_publisher=order_intent_publisher or RecordingOrderIntentPublisher(),
    )


def _event(event_id: str, event_type: str) -> EventEnvelope:
    return EventEnvelope(
        event_id=event_id,
        event_type=event_type,
        schema_version=1,
        occurred_at=NOW,
        received_at=NOW,
        published_at=NOW,
        producer="unit_test",
        correlation_id="corr_strategy_runtime_test",
    )


def _order_intent(strategy_id: StrategyId) -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": f"intent_{strategy_id.removeprefix('strat_')}",
            "strategy_id": strategy_id,
            "market_id": "mkt_strategy_runtime_test",
            "contract_id": "ctr_strategy_runtime_test",
            "outcome_id": "out_yes",
            "side": Side.BUY,
            "quantity": Decimal("1"),
            "limit_price": Decimal("0.50"),
            "created_at": "2026-07-27T15:00:00Z",
            "signal_ids": (SignalId("sig_strategy_runtime_test"),),
            "correlation_id": "corr_strategy_runtime_test",
            "idempotency_key": f"{strategy_id}-intent",
        }
    )


async def _wait_until(predicate: Any) -> None:
    for _ in range(100):
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("condition was not met")
