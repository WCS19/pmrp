"""System clock implementation for production scheduling infrastructure."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from pmrp.clock.protocol import validate_sleep_duration


class SystemClock:
    """Clock backed by the host system time."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    async def sleep(self, duration: timedelta) -> None:
        validated_duration = validate_sleep_duration(duration)
        await asyncio.sleep(validated_duration.total_seconds())
