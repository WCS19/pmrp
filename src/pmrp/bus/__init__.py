"""In-process event bus primitives."""

from pmrp.bus.errors import (
    DuplicateConsumerError,
    EventBusBackpressureError,
    EventBusClosedError,
    EventBusError,
    InvalidQueueSizeError,
)
from pmrp.bus.in_process import InProcessEventBus
from pmrp.bus.protocol import EventBus, EventHandler, EventSubscription
from pmrp.bus.subscription import (
    EventBusHealth,
    EventBusSubscriptionHealth,
    EventConsumerHandle,
    QueuedEventSubscription,
)

__all__ = [
    "DuplicateConsumerError",
    "EventBus",
    "EventBusBackpressureError",
    "EventBusClosedError",
    "EventBusError",
    "EventBusHealth",
    "EventBusSubscriptionHealth",
    "EventConsumerHandle",
    "EventHandler",
    "EventSubscription",
    "InProcessEventBus",
    "InvalidQueueSizeError",
    "QueuedEventSubscription",
]
