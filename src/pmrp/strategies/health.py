"""Strategy runtime health snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pmrp.clock.protocol import normalize_clock_datetime
from pmrp.schemas.enums import HealthStatus, StrategyState
from pmrp.schemas.identifiers import StrategyId


@dataclass(frozen=True, slots=True)
class StrategyRuntimeHealth:
    """Point-in-time health view for one managed strategy instance."""

    strategy_id: StrategyId
    state: StrategyState
    health_status: HealthStatus
    health_message: str | None
    subscribed_event_types: tuple[str, ...]
    processed_events: int
    ignored_events: int
    failed_events: int
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    last_event_at: datetime | None = None
    last_failure_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.strategy_id, StrategyId):
            msg = "strategy_id must be a StrategyId"
            raise TypeError(msg)
        if not isinstance(self.state, StrategyState):
            msg = "state must be a StrategyState"
            raise TypeError(msg)
        if not isinstance(self.health_status, HealthStatus):
            msg = "health_status must be a HealthStatus"
            raise TypeError(msg)
        _validate_nonnegative_count(self.processed_events, field_name="processed_events")
        _validate_nonnegative_count(self.ignored_events, field_name="ignored_events")
        _validate_nonnegative_count(self.failed_events, field_name="failed_events")
        for event_type in self.subscribed_event_types:
            _validate_event_type(event_type)
        object.__setattr__(self, "subscribed_event_types", tuple(self.subscribed_event_types))
        object.__setattr__(self, "started_at", _normalize_optional_datetime(self.started_at))
        object.__setattr__(self, "stopped_at", _normalize_optional_datetime(self.stopped_at))
        object.__setattr__(self, "last_event_at", _normalize_optional_datetime(self.last_event_at))
        object.__setattr__(
            self,
            "last_failure_at",
            _normalize_optional_datetime(self.last_failure_at),
        )


def _validate_nonnegative_count(value: int, *, field_name: str) -> None:
    if type(value) is not int:
        msg = f"{field_name} must be an int"
        raise TypeError(msg)
    if value < 0:
        msg = f"{field_name} must not be negative"
        raise ValueError(msg)


def _validate_event_type(value: str) -> None:
    if type(value) is not str:
        msg = "subscribed_event_types must contain strings"
        raise TypeError(msg)
    if value == "" or value.strip() != value:
        msg = "subscribed_event_types must contain nonempty values without surrounding whitespace"
        raise ValueError(msg)


def _normalize_optional_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return normalize_clock_datetime(value)
