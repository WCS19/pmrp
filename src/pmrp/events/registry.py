"""Event type registry for canonical event factories."""

from __future__ import annotations

import re
from dataclasses import dataclass

from pmrp.schemas.events import (
    MARKET_ORDER_BOOK_DELTA_EVENT_TYPE,
    MARKET_ORDER_BOOK_SNAPSHOT_EVENT_TYPE,
    MARKET_TRADE_OBSERVED_EVENT_TYPE,
    RISK_APPROVED_EVENT_TYPE,
    RISK_CHECK_REQUESTED_EVENT_TYPE,
    RISK_KILL_SWITCH_ACTIVATED_EVENT_TYPE,
    RISK_KILL_SWITCH_RELEASED_EVENT_TYPE,
    RISK_LIMIT_BREACHED_EVENT_TYPE,
    RISK_REJECTED_EVENT_TYPE,
    STRATEGY_HEALTH_CHANGED_EVENT_TYPE,
    STRATEGY_SIGNAL_GENERATED_EVENT_TYPE,
    STRATEGY_STARTED_EVENT_TYPE,
    STRATEGY_STOPPED_EVENT_TYPE,
)
from pmrp.schemas.versions import SchemaVersion, parse_schema_version

_DOTTED_EVENT_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
_CANONICAL_EVENT_SCHEMA_VERSION = 1
_CANONICAL_EVENT_TYPE_SCHEMAS: tuple[tuple[str, str], ...] = (
    (MARKET_ORDER_BOOK_SNAPSHOT_EVENT_TYPE, "order_book_snapshot_event"),
    (MARKET_ORDER_BOOK_DELTA_EVENT_TYPE, "order_book_delta_event"),
    (MARKET_TRADE_OBSERVED_EVENT_TYPE, "trade_observed_event"),
    (STRATEGY_STARTED_EVENT_TYPE, "strategy_started_event"),
    (STRATEGY_STOPPED_EVENT_TYPE, "strategy_stopped_event"),
    (STRATEGY_HEALTH_CHANGED_EVENT_TYPE, "strategy_health_changed_event"),
    (STRATEGY_SIGNAL_GENERATED_EVENT_TYPE, "signal_generated_event"),
    (RISK_CHECK_REQUESTED_EVENT_TYPE, "risk_check_requested_event"),
    (RISK_APPROVED_EVENT_TYPE, "risk_approved_event"),
    (RISK_REJECTED_EVENT_TYPE, "risk_rejected_event"),
    (RISK_LIMIT_BREACHED_EVENT_TYPE, "risk_limit_breached_event"),
    (RISK_KILL_SWITCH_ACTIVATED_EVENT_TYPE, "kill_switch_activated_event"),
    (RISK_KILL_SWITCH_RELEASED_EVENT_TYPE, "kill_switch_released_event"),
)


class UnknownEventTypeError(KeyError):
    """Raised when an event type has no registered schema version."""


@dataclass(frozen=True, slots=True)
class EventTypeRegistration:
    event_type: str
    schema_name: str
    schema_version: SchemaVersion

    def __post_init__(self) -> None:
        _validate_event_type(self.event_type)
        _validate_schema_name(self.schema_name)
        parse_schema_version(self.schema_version)


class EventTypeRegistry:
    """Runtime registry mapping event types to canonical schema versions."""

    def __init__(self, registrations: tuple[EventTypeRegistration, ...] = ()) -> None:
        self._registrations: dict[str, EventTypeRegistration] = {}
        for registration in registrations:
            self.register(registration)

    def register(self, registration: EventTypeRegistration) -> None:
        if registration.event_type in self._registrations:
            msg = f"event type is already registered: {registration.event_type}"
            raise ValueError(msg)
        self._registrations[registration.event_type] = registration

    def get(self, event_type: str) -> EventTypeRegistration:
        _validate_event_type(event_type)
        try:
            return self._registrations[event_type]
        except KeyError as exc:
            msg = f"event type is not registered: {event_type}"
            raise UnknownEventTypeError(msg) from exc

    def schema_version_for(self, event_type: str) -> int:
        return self.get(event_type).schema_version

    def registrations(self) -> tuple[EventTypeRegistration, ...]:
        return tuple(self._registrations.values())


def default_event_type_registrations() -> tuple[EventTypeRegistration, ...]:
    """Return canonical event-type registrations for implemented event schemas."""
    return tuple(
        EventTypeRegistration(
            event_type=event_type,
            schema_name=schema_name,
            schema_version=_CANONICAL_EVENT_SCHEMA_VERSION,
        )
        for event_type, schema_name in _CANONICAL_EVENT_TYPE_SCHEMAS
    )


def default_event_type_registry() -> EventTypeRegistry:
    """Create a fresh registry containing canonical event schema mappings."""
    return EventTypeRegistry(default_event_type_registrations())


def _validate_event_type(event_type: str) -> None:
    if _DOTTED_EVENT_TYPE_PATTERN.fullmatch(event_type) is None:
        msg = "event_type must use dotted lowercase segments"
        raise ValueError(msg)


def _validate_schema_name(schema_name: str) -> None:
    if re.fullmatch(r"^[a-z][a-z0-9_]*$", schema_name) is None:
        msg = "schema_name must use lowercase snake_case"
        raise ValueError(msg)
