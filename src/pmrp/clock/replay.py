"""Deterministic replay clock implementation."""

from __future__ import annotations

from datetime import datetime, timedelta

from pmrp.clock.protocol import normalize_clock_datetime, validate_sleep_duration


class ReplayClock:
    """Bounded virtual clock for deterministic replay timelines."""

    __slots__ = ("_current_time", "_ends_at", "_starts_at")

    def __init__(
        self,
        *,
        starts_at: datetime,
        ends_at: datetime,
        current_time: datetime | None = None,
    ) -> None:
        self._starts_at = normalize_clock_datetime(starts_at)
        self._ends_at = normalize_clock_datetime(ends_at)
        if self._ends_at < self._starts_at:
            msg = "replay clock ends_at must not precede starts_at"
            raise ValueError(msg)
        self._current_time = self._normalize_replay_time(current_time or self._starts_at)

    @property
    def starts_at(self) -> datetime:
        return self._starts_at

    @property
    def ends_at(self) -> datetime:
        return self._ends_at

    def now(self) -> datetime:
        return self._current_time

    def advance(self, duration: timedelta) -> datetime:
        validated_duration = validate_sleep_duration(duration)
        return self.advance_to(self._current_time + validated_duration)

    def advance_to(self, current_time: datetime) -> datetime:
        self._current_time = self._normalize_replay_time(current_time)
        return self._current_time

    def reset(self) -> datetime:
        self._current_time = self._starts_at
        return self._current_time

    async def sleep(self, duration: timedelta) -> None:
        self.advance(duration)

    def _normalize_replay_time(self, current_time: datetime) -> datetime:
        normalized_time = normalize_clock_datetime(current_time)
        if normalized_time < self._starts_at or normalized_time > self._ends_at:
            msg = "replay clock time must be within the replay window"
            raise ValueError(msg)
        return normalized_time
