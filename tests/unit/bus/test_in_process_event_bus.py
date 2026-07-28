from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from pmrp.bus import (
    DuplicateConsumerError,
    EventBusBackpressureError,
    EventBusClosedError,
    InProcessEventBus,
    InvalidQueueSizeError,
)

pytestmark = pytest.mark.unit


@dataclass(frozen=True, slots=True)
class _TestEvent:
    sequence: int
    partition: str | None = None


@dataclass(frozen=True, slots=True)
class _OtherEvent:
    sequence: int


async def test_single_publisher_delivers_event_to_subscriber() -> None:
    bus = InProcessEventBus()
    subscription = bus.subscribe(_TestEvent, consumer_name="research-consumer")
    event = _TestEvent(sequence=1)

    await bus.publish(event)

    assert await subscription.__anext__() == event
    assert bus.health().published_events == 1
    assert bus.health().delivered_events == 1


async def test_multiple_subscribers_each_receive_event() -> None:
    bus = InProcessEventBus()
    first = bus.subscribe(_TestEvent, consumer_name="first-consumer")
    second = bus.subscribe(_TestEvent, consumer_name="second-consumer")
    event = _TestEvent(sequence=1)

    await bus.publish(event)

    assert await first.__anext__() == event
    assert await second.__anext__() == event
    assert bus.health().delivered_events == 2


async def test_full_queue_raises_backpressure_without_partial_delivery() -> None:
    bus = InProcessEventBus(default_queue_size=1)
    first = bus.subscribe(_TestEvent, consumer_name="first-consumer")
    second = bus.subscribe(_TestEvent, consumer_name="second-consumer")
    first.publish_nowait(_TestEvent(sequence=100))
    event = _TestEvent(sequence=1)

    with pytest.raises(EventBusBackpressureError) as exc_info:
        await bus.publish(event)

    assert exc_info.value.consumer_names == ("first-consumer",)
    assert bus.health().backpressure_events == 1
    assert bus.health().delivered_events == 0
    assert await first.__anext__() == _TestEvent(sequence=100)
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(second.__anext__(), timeout=0.01)


async def test_consumer_exception_does_not_stop_unrelated_consumer() -> None:
    bus = InProcessEventBus()
    failing_called = asyncio.Event()
    successful_called = asyncio.Event()
    successful_events: list[_TestEvent] = []

    async def failing_handler(event: _TestEvent) -> None:
        del event
        failing_called.set()
        raise RuntimeError("handler failure")

    async def successful_handler(event: _TestEvent) -> None:
        successful_events.append(event)
        successful_called.set()

    failing_handle = bus.start_consumer(
        _TestEvent,
        consumer_name="failing-consumer",
        handler=failing_handler,
    )
    successful_handle = bus.start_consumer(
        _TestEvent,
        consumer_name="successful-consumer",
        handler=successful_handler,
    )

    await bus.publish(_TestEvent(sequence=1))
    await asyncio.wait_for(failing_called.wait(), timeout=1)
    await asyncio.wait_for(successful_called.wait(), timeout=1)

    assert failing_handle.failure_count == 1
    assert successful_handle.failure_count == 0
    assert successful_events == [_TestEvent(sequence=1)]
    assert bus.health().consumer_failures == 1
    await bus.close()


async def test_shutdown_closes_subscriptions_and_managed_consumer_tasks() -> None:
    bus = InProcessEventBus()

    async def handler(event: _TestEvent) -> None:
        del event

    handle = bus.start_consumer(_TestEvent, consumer_name="consumer", handler=handler)

    await bus.close()

    assert bus.health().closed is True
    assert handle.task.done()
    with pytest.raises(EventBusClosedError):
        await bus.publish(_TestEvent(sequence=1))


async def test_subscription_close_preserves_pending_event_when_queue_is_full() -> None:
    bus = InProcessEventBus(default_queue_size=1)
    subscription = bus.subscribe(_TestEvent, consumer_name="consumer")
    event = _TestEvent(sequence=1)

    await bus.publish(event)
    await bus.close()

    assert await subscription.__anext__() == event
    with pytest.raises(StopAsyncIteration):
        await subscription.__anext__()
    assert subscription.queue_depth == 0


async def test_publish_waiting_behind_close_fails_without_delivery() -> None:
    bus = InProcessEventBus()
    subscription = bus.subscribe(_TestEvent, consumer_name="consumer")
    await bus._publish_lock.acquire()
    close_task = asyncio.create_task(bus.close())
    publish_task = asyncio.create_task(bus.publish(_TestEvent(sequence=1)))
    await asyncio.sleep(0)

    bus._publish_lock.release()
    await close_task

    with pytest.raises(EventBusClosedError):
        await publish_task
    assert bus.health().published_events == 0
    assert bus.health().delivered_events == 0
    assert subscription.closed is True


async def test_duplicate_publish_is_explicitly_delivered_twice() -> None:
    bus = InProcessEventBus()
    subscription = bus.subscribe(_TestEvent, consumer_name="consumer")
    event = _TestEvent(sequence=1)

    await bus.publish(event)
    await bus.publish(event)

    assert await subscription.__anext__() == event
    assert await subscription.__anext__() == event
    assert bus.health().published_events == 2
    assert bus.health().delivered_events == 2


async def test_partitioned_events_route_only_to_matching_subscription() -> None:
    bus = InProcessEventBus()
    alpha = bus.subscribe(_TestEvent, consumer_name="alpha-consumer", partition_key="alpha")
    beta = bus.subscribe(_TestEvent, consumer_name="beta-consumer", partition_key="beta")
    alpha_event = _TestEvent(sequence=1, partition="alpha")
    beta_event = _TestEvent(sequence=2, partition="beta")

    await bus.publish(alpha_event, partition_key="alpha")
    await bus.publish(beta_event, partition_key="beta")

    assert await alpha.__anext__() == alpha_event
    assert await beta.__anext__() == beta_event
    assert bus.health().delivered_events == 2


async def test_partitioned_events_preserve_fifo_order_per_subscription() -> None:
    bus = InProcessEventBus()
    subscription = bus.subscribe(_TestEvent, consumer_name="alpha-consumer", partition_key="alpha")

    for sequence in range(5):
        await bus.publish(_TestEvent(sequence=sequence), partition_key="alpha")

    received = [await subscription.__anext__() for _ in range(5)]

    assert received == [_TestEvent(sequence=sequence) for sequence in range(5)]


async def test_deterministic_mode_uses_stable_delivery_order() -> None:
    bus = InProcessEventBus(deterministic=True)
    bus.subscribe(_TestEvent, consumer_name="z-consumer")
    bus.subscribe(_TestEvent, consumer_name="a-consumer")

    await bus.publish(_TestEvent(sequence=1))

    assert bus.health().last_delivery_order == ("a-consumer", "z-consumer")


async def test_cancel_subscriber_releases_resources() -> None:
    bus = InProcessEventBus()
    subscription = bus.subscribe(_TestEvent, consumer_name="consumer")

    await subscription.close()

    assert bus.health().subscriptions == ()


async def test_unsupported_event_is_ignored_by_policy() -> None:
    bus = InProcessEventBus()
    subscription = bus.subscribe(_TestEvent, consumer_name="consumer")

    await bus.publish(_OtherEvent(sequence=1))

    assert bus.health().published_events == 1
    assert bus.health().delivered_events == 0
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(subscription.__anext__(), timeout=0.01)


def test_duplicate_consumer_name_is_rejected() -> None:
    bus = InProcessEventBus()
    bus.subscribe(_TestEvent, consumer_name="consumer")

    with pytest.raises(DuplicateConsumerError):
        bus.subscribe(_TestEvent, consumer_name="consumer")


def test_explicit_zero_queue_size_is_rejected() -> None:
    bus = InProcessEventBus()

    with pytest.raises(InvalidQueueSizeError, match="queue_size must be positive"):
        bus.subscribe(_TestEvent, consumer_name="consumer", queue_size=0)
