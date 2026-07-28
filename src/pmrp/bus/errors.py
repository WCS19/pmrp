"""Event bus error types."""

from __future__ import annotations


class EventBusError(Exception):
    """Base class for event bus failures."""


class EventBusClosedError(EventBusError):
    """Raised when an operation is attempted on a closed bus."""


class EventBusBackpressureError(EventBusError):
    """Raised when bounded subscriber queues cannot accept an event."""

    def __init__(self, consumer_names: tuple[str, ...]) -> None:
        self.consumer_names = consumer_names
        super().__init__("event bus subscriber queue is full")


class DuplicateConsumerError(EventBusError):
    """Raised when a consumer name is already registered."""


class InvalidQueueSizeError(EventBusError):
    """Raised when a subscription queue size is invalid."""
