"""Strategy context behavior tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

import pytest

from pmrp.bus import InProcessEventBus
from pmrp.clock import FrozenClock
from pmrp.schemas.enums import Side
from pmrp.schemas.identifiers import StrategyId
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.strategy import Signal, SignalDirection
from pmrp.strategies import StrategyContext, StrategyContextError, StrategyEmissionError

pytestmark = pytest.mark.unit

STRATEGY_ID = StrategyId("strat_context_test_v1")
OTHER_STRATEGY_ID = StrategyId("strat_other_test_v1")
NOW = datetime(2026, 7, 27, 15, 0, tzinfo=UTC)


def test_strategy_context_delegates_time_to_injected_clock() -> None:
    context = _context(clock=FrozenClock(NOW))

    assert context.now() == NOW


async def test_strategy_context_subscribes_through_injected_event_bus() -> None:
    event_bus = InProcessEventBus()
    context = _context(event_bus=event_bus)

    subscription = context.subscribe(
        DemoEvent,
        consumer_name="strategy-context-test",
        queue_size=1,
    )

    assert subscription.consumer_name == "strategy-context-test"
    assert subscription.event_type is DemoEvent
    await event_bus.close()


async def test_strategy_context_wraps_subscription_failures_safely() -> None:
    context = _context(event_bus=FailingEventBus())

    with pytest.raises(StrategyContextError) as exc_info:
        context.subscribe(DemoEvent, consumer_name="strategy-context-test")

    assert str(exc_info.value) == "Strategy event subscription failed"
    assert exc_info.value.reason_code == "strategy_context_subscription_failed"
    assert exc_info.value.context["strategy_id"] == STRATEGY_ID
    assert "raw_sensitive_payload" not in str(exc_info.value)
    assert "raw_sensitive_payload" not in exc_info.value.context.values()
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__ is True


async def test_strategy_context_publishes_matching_strategy_signal() -> None:
    signal_publisher = RecordingSignalPublisher()
    context = _context(signal_publisher=signal_publisher)
    signal = _signal()

    await context.publish_signal(signal)

    assert signal_publisher.signals == [signal]


async def test_strategy_context_rejects_signal_from_different_strategy() -> None:
    context = _context()
    signal = _signal(strategy_id=OTHER_STRATEGY_ID)

    with pytest.raises(StrategyEmissionError) as exc_info:
        await context.publish_signal(signal)

    assert str(exc_info.value) == "Signal strategy_id must match the active strategy context"
    assert exc_info.value.reason_code == "strategy_signal_strategy_id_mismatch"
    assert exc_info.value.context["context_strategy_id"] == STRATEGY_ID
    assert exc_info.value.context["signal_strategy_id"] == OTHER_STRATEGY_ID


async def test_strategy_context_wraps_signal_publisher_failures_safely() -> None:
    context = _context(signal_publisher=FailingSignalPublisher())

    with pytest.raises(StrategyEmissionError) as exc_info:
        await context.publish_signal(_signal())

    assert str(exc_info.value) == "Strategy signal emission failed"
    assert exc_info.value.reason_code == "strategy_signal_emission_failed"
    assert "raw_sensitive_payload" not in str(exc_info.value)
    assert "raw_sensitive_payload" not in exc_info.value.context.values()
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__ is True


async def test_strategy_context_publishes_matching_order_intent() -> None:
    intent_publisher = RecordingOrderIntentPublisher()
    context = _context(order_intent_publisher=intent_publisher)
    intent = _order_intent()

    await context.publish_order_intent(intent)

    assert intent_publisher.intents == [intent]


async def test_strategy_context_blocks_disabled_order_intent_emission() -> None:
    context = _context(order_intents_enabled=False)

    with pytest.raises(StrategyEmissionError) as exc_info:
        await context.publish_order_intent(_order_intent())

    assert (
        str(exc_info.value) == "Order intent emission is disabled for the active strategy context"
    )
    assert exc_info.value.reason_code == "strategy_order_intent_emission_disabled"


async def test_strategy_context_rejects_order_intent_from_different_strategy() -> None:
    context = _context()
    intent = _order_intent(strategy_id=OTHER_STRATEGY_ID)

    with pytest.raises(StrategyEmissionError) as exc_info:
        await context.publish_order_intent(intent)

    assert str(exc_info.value) == "OrderIntent strategy_id must match the active strategy context"
    assert exc_info.value.reason_code == "strategy_order_intent_strategy_id_mismatch"
    assert exc_info.value.context["context_strategy_id"] == STRATEGY_ID
    assert exc_info.value.context["intent_strategy_id"] == OTHER_STRATEGY_ID


async def test_strategy_context_wraps_order_intent_publisher_failures_safely() -> None:
    context = _context(order_intent_publisher=FailingOrderIntentPublisher())

    with pytest.raises(StrategyEmissionError) as exc_info:
        await context.publish_order_intent(_order_intent())

    assert str(exc_info.value) == "Strategy order intent emission failed"
    assert exc_info.value.reason_code == "strategy_order_intent_emission_failed"
    assert "raw_sensitive_payload" not in str(exc_info.value)
    assert "raw_sensitive_payload" not in exc_info.value.context.values()
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__ is True


def test_strategy_context_exposes_only_approved_optional_services() -> None:
    market_data = object()
    context = _context(services={"market_data": market_data})

    assert context.service("market_data") is market_data
    assert context.service("metrics") is None

    with pytest.raises(TypeError):
        cast(Any, context.services)["metrics"] = object()


def test_strategy_context_rejects_forbidden_services() -> None:
    with pytest.raises(StrategyContextError) as exc_info:
        _context(services={"exchange_client": object()})

    assert str(exc_info.value) == "Strategy context service is not approved for strategy access"
    assert exc_info.value.reason_code == "strategy_context_service_not_approved"
    assert exc_info.value.context["service_name"] == "exchange_client"


def test_strategy_context_rejects_unapproved_services() -> None:
    with pytest.raises(StrategyContextError, match="not approved"):
        _context(services={"database": object()})


def test_strategy_context_freezes_metadata_and_rejects_floats() -> None:
    context = _context(metadata={"mode": "replay", "nested": {"attempt": 1}})

    assert context.metadata["mode"] == "replay"
    with pytest.raises(TypeError):
        cast(Any, context.metadata)["mode"] = "paper"
    with pytest.raises(TypeError, match="must not contain floats"):
        _context(metadata={"confidence": 0.5})


def test_strategy_context_rejects_sensitive_metadata_keys() -> None:
    with pytest.raises(StrategyContextError) as exc_info:
        _context(metadata={"api-token": "not-logged"})

    assert str(exc_info.value) == "Strategy context metadata must not include sensitive key names"
    assert exc_info.value.reason_code == "strategy_context_sensitive_metadata_key"
    assert exc_info.value.context["metadata_key"] == "api-token"


def test_strategy_context_rejects_untyped_strategy_identifier() -> None:
    with pytest.raises(TypeError, match="strategy_id must be a StrategyId"):
        StrategyContext(
            strategy_id=cast(Any, "strat_context_test_v1"),
            clock=FrozenClock(NOW),
            event_bus=InProcessEventBus(),
            signal_publisher=RecordingSignalPublisher(),
            order_intent_publisher=RecordingOrderIntentPublisher(),
        )


class DemoEvent:
    pass


class RecordingSignalPublisher:
    def __init__(self) -> None:
        self.signals: list[Signal] = []

    async def publish_signal(self, signal: Signal) -> None:
        self.signals.append(signal)


class RecordingOrderIntentPublisher:
    def __init__(self) -> None:
        self.intents: list[OrderIntent] = []

    async def publish_order_intent(self, intent: OrderIntent) -> None:
        self.intents.append(intent)


class FailingSignalPublisher:
    async def publish_signal(self, signal: Signal) -> None:
        del signal
        raise RuntimeError("raw_sensitive_payload")


class FailingOrderIntentPublisher:
    async def publish_order_intent(self, intent: OrderIntent) -> None:
        del intent
        raise RuntimeError("raw_sensitive_payload")


class FailingEventBus:
    async def publish(self, event: object, *, partition_key: str | None = None) -> None:
        del event, partition_key

    def subscribe(
        self,
        event_type: type[Any],
        *,
        consumer_name: str,
        partition_key: str | None = None,
        queue_size: int | None = None,
    ) -> object:
        del event_type, consumer_name, partition_key, queue_size
        raise RuntimeError("raw_sensitive_payload")

    async def close(self) -> None:
        return None


def _context(
    *,
    clock: FrozenClock | None = None,
    event_bus: Any | None = None,
    signal_publisher: Any | None = None,
    order_intent_publisher: Any | None = None,
    order_intents_enabled: bool = True,
    services: dict[str, object] | None = None,
    metadata: dict[str, object] | None = None,
) -> StrategyContext:
    return StrategyContext(
        strategy_id=STRATEGY_ID,
        clock=clock or FrozenClock(NOW),
        event_bus=event_bus or InProcessEventBus(),
        signal_publisher=signal_publisher or RecordingSignalPublisher(),
        order_intent_publisher=order_intent_publisher or RecordingOrderIntentPublisher(),
        order_intents_enabled=order_intents_enabled,
        services=services or {},
        metadata=metadata or {},
    )


def _signal(*, strategy_id: StrategyId = STRATEGY_ID) -> Signal:
    return Signal.model_validate(
        {
            "signal_id": "sig_strategy_context_test",
            "strategy_id": strategy_id,
            "market_id": "mkt_strategy_context_test",
            "signal_type": "threshold",
            "direction": SignalDirection.BUY,
            "strength": "0.75",
            "fair_probability": "0.58",
            "confidence": "0.80",
            "valid_from": "2026-07-27T15:00:00Z",
            "reason_code": "THRESHOLD_CROSSED",
            "correlation_id": "corr_strategy_context_test",
        }
    )


def _order_intent(*, strategy_id: StrategyId = STRATEGY_ID) -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_strategy_context_test",
            "strategy_id": strategy_id,
            "market_id": "mkt_strategy_context_test",
            "contract_id": "ctr_strategy_context_test",
            "outcome_id": "out_yes",
            "side": Side.BUY,
            "quantity": Decimal("2"),
            "limit_price": Decimal("0.42"),
            "created_at": "2026-07-27T15:00:00Z",
            "correlation_id": "corr_strategy_context_test",
            "idempotency_key": "strategy-context-test-intent",
        }
    )
