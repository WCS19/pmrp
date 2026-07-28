"""Deterministic clock implementations for tests and fixed-time workflows."""

from __future__ import annotations

from datetime import datetime, timedelta

from pmrp.clock.protocol import normalize_clock_datetime, validate_sleep_duration


class FrozenClock:
    """Clock fixed at one timezone-aware UTC timestamp."""

    __slots__ = ("_current_time",)

    def __init__(self, current_time: datetime) -> None:
        self._current_time = normalize_clock_datetime(current_time)

    def now(self) -> datetime:
        return self._current_time

    async def sleep(self, duration: timedelta) -> None:
        validate_sleep_duration(duration)


class AdvancingTestClock:
    """Deterministic test clock whose sleeps advance virtual time exactly."""

    __slots__ = ("_current_time",)

    def __init__(self, current_time: datetime) -> None:
        self._current_time = normalize_clock_datetime(current_time)

    def now(self) -> datetime:
        return self._current_time

    def set(self, current_time: datetime) -> datetime:
        self._current_time = normalize_clock_datetime(current_time)
        return self._current_time

    def advance(self, duration: timedelta) -> datetime:
        validated_duration = validate_sleep_duration(duration)
        self._current_time = self._current_time + validated_duration
        return self._current_time

    async def sleep(self, duration: timedelta) -> None:
        self.advance(duration)
