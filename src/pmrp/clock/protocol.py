"""Clock protocol and shared clock validation helpers."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol, runtime_checkable

from pmrp.schemas.time import parse_utc_datetime


@runtime_checkable
class Clock(Protocol):
    """Injected time source used outside approved clock infrastructure."""

    def now(self) -> datetime:
        """Return the current timezone-aware UTC time."""
        ...

    async def sleep(self, duration: timedelta) -> None:
        """Wait according to this clock's time model."""
        ...


def normalize_clock_datetime(value: datetime) -> datetime:
    """Normalize a clock timestamp to timezone-aware UTC."""

    return parse_utc_datetime(value)


def validate_sleep_duration(duration: timedelta) -> timedelta:
    """Reject non-timedelta and negative sleep durations."""

    if not isinstance(duration, timedelta):
        msg = "sleep duration must be a timedelta"
        raise TypeError(msg)
    if duration < timedelta(0):
        msg = "sleep duration must not be negative"
        raise ValueError(msg)
    return duration
