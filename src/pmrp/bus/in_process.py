"""In-process asynchronous event bus."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any, TypeVar, cast

from pmrp.bus.errors import DuplicateConsumerError, EventBusBackpressureError, EventBusClosedError
from pmrp.bus.protocol import EventHandler
from pmrp.bus.subscription import (
    EventBusHealth,
    EventConsumerHandle,
    QueuedEventSubscription,
)

T = TypeVar("T")


class InProcessEventBus:
    """Bounded in-process event bus for modular-monolith runtime components."""

    def __init__(
        self,
        *,
        default_queue_size: int = 1024,
        deterministic: bool = False,
        shutdown_timeout_seconds: float = 5.0,
    ) -> None:
        if default_queue_size < 1:
            msg = "default_queue_size must be positive"
            raise ValueError(msg)
        if shutdown_timeout_seconds < 0:
            msg = "shutdown_timeout_seconds must not be negative"
            raise ValueError(msg)
        self._default_queue_size = default_queue_size
        self._deterministic = deterministic
        self._shutdown_timeout_seconds = shutdown_timeout_seconds
        self._subscriptions: dict[str, QueuedEventSubscription[Any]] = {}
        self._consumer_handles: dict[str, EventConsumerHandle[Any]] = {}
        self._publish_lock = asyncio.Lock()
        self._closed = False
        self._published_events = 0
        self._delivered_events = 0
        self._backpressure_events = 0
        self._last_delivery_order: tuple[str, ...] = ()

    async def publish(self, event: object, *, partition_key: str | None = None) -> None:
        if self._closed:
            msg = "event bus is closed"
            raise EventBusClosedError(msg)
        effective_partition_key = _event_partition_key(event, explicit_partition_key=partition_key)
        async with self._publish_lock:
            subscriptions = self._matching_subscriptions(event, effective_partition_key)
            full_subscriptions = tuple(
                subscription.consumer_name for subscription in subscriptions if subscription.full()
            )
            if full_subscriptions:
                self._backpressure_events += 1
                raise EventBusBackpressureError(full_subscriptions)

            for subscription in subscriptions:
                subscription.publish_nowait(cast(Any, event))

            self._published_events += 1
            self._delivered_events += len(subscriptions)
            self._last_delivery_order = tuple(
                subscription.consumer_name for subscription in subscriptions
            )

    def subscribe(
        self,
        event_type: type[T],
        *,
        consumer_name: str,
        partition_key: str | None = None,
        queue_size: int | None = None,
    ) -> QueuedEventSubscription[T]:
        if self._closed:
            msg = "event bus is closed"
            raise EventBusClosedError(msg)
        _validate_consumer_name(consumer_name)
        if consumer_name in self._subscriptions:
            msg = f"consumer is already registered: {consumer_name}"
            raise DuplicateConsumerError(msg)
        subscription: QueuedEventSubscription[T] = QueuedEventSubscription(
            event_type=event_type,
            consumer_name=consumer_name,
            partition_key=partition_key,
            queue_size=queue_size or self._default_queue_size,
            on_close=self._remove_subscription,
        )
        self._subscriptions[consumer_name] = subscription
        return subscription

    def start_consumer(
        self,
        event_type: type[T],
        *,
        consumer_name: str,
        handler: EventHandler[T],
        partition_key: str | None = None,
        queue_size: int | None = None,
    ) -> EventConsumerHandle[T]:
        subscription = self.subscribe(
            event_type,
            consumer_name=consumer_name,
            partition_key=partition_key,
            queue_size=queue_size,
        )
        handle: EventConsumerHandle[T] = EventConsumerHandle(
            consumer_name=consumer_name,
            subscription=subscription,
        )

        async def consume() -> None:
            async for event in subscription:
                try:
                    await handler(event)
                except Exception as exc:
                    handle.record_failure(exc)

        task = asyncio.create_task(consume(), name=f"pmrp-event-bus-{consumer_name}")
        handle.attach_task(task)
        self._consumer_handles[consumer_name] = handle
        return handle

    def health(self) -> EventBusHealth:
        subscriptions = tuple(
            subscription.health()
            for subscription in self._ordered_subscriptions(self._subscriptions.values())
        )
        return EventBusHealth(
            closed=self._closed,
            deterministic=self._deterministic,
            subscriptions=subscriptions,
            published_events=self._published_events,
            delivered_events=self._delivered_events,
            backpressure_events=self._backpressure_events,
            consumer_failures=sum(
                handle.failure_count for handle in self._consumer_handles.values()
            ),
            last_delivery_order=self._last_delivery_order,
        )

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        subscriptions = tuple(self._subscriptions.values())
        for subscription in subscriptions:
            await subscription.close()

        tasks = tuple(handle.task for handle in self._consumer_handles.values())
        if not tasks:
            return
        done, pending = await asyncio.wait(tasks, timeout=self._shutdown_timeout_seconds)
        del done
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    def _matching_subscriptions(
        self,
        event: object,
        partition_key: str | None,
    ) -> tuple[QueuedEventSubscription[Any], ...]:
        subscriptions = self._ordered_subscriptions(self._subscriptions.values())
        return tuple(
            subscription
            for subscription in subscriptions
            if not subscription.closed
            and isinstance(event, subscription.event_type)
            and (subscription.partition_key is None or subscription.partition_key == partition_key)
        )

    def _ordered_subscriptions(
        self,
        subscriptions: Iterable[QueuedEventSubscription[Any]],
    ) -> tuple[QueuedEventSubscription[Any], ...]:
        if not self._deterministic:
            return tuple(subscriptions)
        return tuple(
            sorted(
                subscriptions,
                key=lambda subscription: (
                    subscription.consumer_name,
                    subscription.event_type.__module__,
                    subscription.event_type.__qualname__,
                    subscription.partition_key or "",
                ),
            )
        )

    def _remove_subscription(self, consumer_name: str) -> None:
        self._subscriptions.pop(consumer_name, None)


def _validate_consumer_name(consumer_name: str) -> None:
    if consumer_name == "" or consumer_name.strip() != consumer_name:
        msg = "consumer_name must be nonempty without surrounding whitespace"
        raise ValueError(msg)


def _event_partition_key(event: object, *, explicit_partition_key: str | None) -> str | None:
    if explicit_partition_key is not None:
        return explicit_partition_key
    market_id = getattr(event, "market_id", None)
    if market_id is not None:
        return str(market_id)
    return None
