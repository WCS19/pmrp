"""Event bus subscription state and health snapshots."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import TypeVar

from pmrp.bus.errors import EventBusBackpressureError, EventBusClosedError, InvalidQueueSizeError

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class EventBusSubscriptionHealth:
    consumer_name: str
    event_type: str
    partition_key: str | None
    queue_depth: int
    max_queue_size: int
    closed: bool


@dataclass(frozen=True, slots=True)
class EventBusHealth:
    closed: bool
    deterministic: bool
    subscriptions: tuple[EventBusSubscriptionHealth, ...]
    published_events: int
    delivered_events: int
    backpressure_events: int
    consumer_failures: int
    last_delivery_order: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ClosedSubscription:
    pass


_CLOSED = _ClosedSubscription()
type _QueueItem[T] = T | _ClosedSubscription


class QueuedEventSubscription[T]:
    """Bounded FIFO event subscription."""

    def __init__(
        self,
        *,
        event_type: type[T],
        consumer_name: str,
        partition_key: str | None,
        queue_size: int,
        on_close: Callable[[str], None] | None = None,
    ) -> None:
        if queue_size < 1:
            msg = "queue_size must be positive"
            raise InvalidQueueSizeError(msg)
        self._event_type = event_type
        self._consumer_name = consumer_name
        self._partition_key = partition_key
        self._queue_size = queue_size
        self._queue: asyncio.Queue[_QueueItem[T]] = asyncio.Queue(maxsize=queue_size + 1)
        self._pending_events = 0
        self._on_close = on_close
        self._closed = False

    @property
    def consumer_name(self) -> str:
        return self._consumer_name

    @property
    def event_type(self) -> type[T]:
        return self._event_type

    @property
    def partition_key(self) -> str | None:
        return self._partition_key

    @property
    def queue_depth(self) -> int:
        return self._pending_events

    @property
    def max_queue_size(self) -> int:
        return self._queue_size

    @property
    def closed(self) -> bool:
        return self._closed

    def full(self) -> bool:
        return self._pending_events >= self._queue_size

    def publish_nowait(self, event: T) -> None:
        if self._closed:
            msg = "event subscription is closed"
            raise EventBusClosedError(msg)
        if self.full():
            raise EventBusBackpressureError((self._consumer_name,))
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull as exc:
            raise EventBusBackpressureError((self._consumer_name,)) from exc
        self._pending_events += 1

    def __aiter__(self) -> AsyncIterator[T]:
        return self

    async def __anext__(self) -> T:
        item = await self._queue.get()
        if isinstance(item, _ClosedSubscription):
            raise StopAsyncIteration
        self._pending_events -= 1
        return item

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._queue.put_nowait(_CLOSED)
        if self._on_close is not None:
            self._on_close(self._consumer_name)

    def health(self) -> EventBusSubscriptionHealth:
        return EventBusSubscriptionHealth(
            consumer_name=self._consumer_name,
            event_type=f"{self._event_type.__module__}.{self._event_type.__qualname__}",
            partition_key=self._partition_key,
            queue_depth=self.queue_depth,
            max_queue_size=self._queue_size,
            closed=self._closed,
        )


class EventConsumerHandle[T]:
    """Handle for a managed event consumer task."""

    def __init__(
        self,
        *,
        consumer_name: str,
        subscription: QueuedEventSubscription[T],
    ) -> None:
        self._consumer_name = consumer_name
        self._subscription = subscription
        self._task: asyncio.Task[None] | None = None
        self._failure_count = 0
        self._last_error_type: str | None = None

    @property
    def consumer_name(self) -> str:
        return self._consumer_name

    @property
    def subscription(self) -> QueuedEventSubscription[T]:
        return self._subscription

    @property
    def task(self) -> asyncio.Task[None]:
        if self._task is None:
            msg = "consumer task has not been attached"
            raise RuntimeError(msg)
        return self._task

    @property
    def failure_count(self) -> int:
        return self._failure_count

    @property
    def last_error_type(self) -> str | None:
        return self._last_error_type

    def attach_task(self, task: asyncio.Task[None]) -> None:
        if self._task is not None:
            msg = "consumer task is already attached"
            raise RuntimeError(msg)
        self._task = task

    def record_failure(self, exc: Exception) -> None:
        self._failure_count += 1
        self._last_error_type = type(exc).__name__

    async def close(self) -> None:
        await self._subscription.close()
        if self._task is None or self._task.done():
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
