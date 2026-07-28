"""Event bus protocols."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Protocol, TypeVar

T = TypeVar("T")
T_co = TypeVar("T_co", covariant=True)

type EventHandler[T] = Callable[[T], Awaitable[None]]


class EventSubscription(Protocol[T_co]):
    """Asynchronous typed event subscription."""

    @property
    def consumer_name(self) -> str: ...

    @property
    def event_type(self) -> type[T_co]: ...

    @property
    def partition_key(self) -> str | None: ...

    def __aiter__(self) -> AsyncIterator[T_co]: ...

    async def close(self) -> None: ...


class EventBus(Protocol):
    """In-process event bus interface."""

    async def publish(self, event: object, *, partition_key: str | None = None) -> None: ...

    def subscribe(
        self,
        event_type: type[T],
        *,
        consumer_name: str,
        partition_key: str | None = None,
        queue_size: int | None = None,
    ) -> EventSubscription[T]: ...

    async def close(self) -> None: ...
