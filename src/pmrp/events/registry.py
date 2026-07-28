"""Event type registry for canonical event factories."""

from __future__ import annotations

import re
from dataclasses import dataclass

from pmrp.schemas.versions import SchemaVersion, parse_schema_version

_DOTTED_EVENT_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")


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


def _validate_event_type(event_type: str) -> None:
    if _DOTTED_EVENT_TYPE_PATTERN.fullmatch(event_type) is None:
        msg = "event_type must use dotted lowercase segments"
        raise ValueError(msg)


def _validate_schema_name(schema_name: str) -> None:
    if re.fullmatch(r"^[a-z][a-z0-9_]*$", schema_name) is None:
        msg = "schema_name must use lowercase snake_case"
        raise ValueError(msg)
