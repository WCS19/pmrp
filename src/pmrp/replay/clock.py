"""Replay clock helpers bound to replay manifests and events."""

from __future__ import annotations

from datetime import datetime

from pmrp.clock import ReplayClock
from pmrp.replay.errors import ReplayClockError
from pmrp.schemas.events import EventEnvelope
from pmrp.schemas.identifiers import ReplaySessionId
from pmrp.schemas.replay import ReplayManifest


def build_replay_clock(
    manifest: ReplayManifest,
    *,
    current_time: datetime | None = None,
) -> ReplayClock:
    """Create a bounded injected replay clock from a validated manifest."""

    clock = _try_build_replay_clock(manifest, current_time=current_time)
    if clock is None:
        raise ReplayClockError(
            "Replay clock could not be initialized from manifest",
            reason_code="replay_clock_initialization_failed",
            context={
                "replay_session_id": str(manifest.replay_session_id),
                "dataset_id": manifest.dataset_id,
            },
        )
    return clock


def advance_replay_clock_to_event(
    clock: ReplayClock,
    event: EventEnvelope,
    *,
    replay_session_id: ReplaySessionId | None = None,
) -> datetime:
    """Advance a replay clock monotonically to a replay event occurrence time."""

    if event.replay_session_id is None:
        raise ReplayClockError(
            "Replay event must include replay_session_id before clock advancement",
            reason_code="replay_clock_event_session_missing",
            context={"event_id": str(event.event_id)},
        )
    if replay_session_id is not None and event.replay_session_id != replay_session_id:
        raise ReplayClockError(
            "Replay event replay_session_id does not match clock replay_session_id",
            reason_code="replay_clock_event_session_mismatch",
            context={
                "event_id": str(event.event_id),
                "expected_replay_session_id": str(replay_session_id),
                "actual_replay_session_id": str(event.replay_session_id),
            },
        )
    if event.occurred_at < clock.now():
        raise ReplayClockError(
            "Replay event occurrence time cannot move clock backward",
            reason_code="replay_clock_event_time_reversed",
            context={"event_id": str(event.event_id)},
        )
    advanced_time = _try_advance_clock_to_event(clock, event)
    if advanced_time is None:
        raise ReplayClockError(
            "Replay event occurrence time is outside the replay clock window",
            reason_code="replay_clock_event_out_of_window",
            context={"event_id": str(event.event_id)},
        )
    return advanced_time


def _try_build_replay_clock(
    manifest: ReplayManifest,
    *,
    current_time: datetime | None,
) -> ReplayClock | None:
    try:
        return ReplayClock(
            starts_at=manifest.starts_at,
            ends_at=manifest.ends_at,
            current_time=current_time,
        )
    except (TypeError, ValueError):
        return None


def _try_advance_clock_to_event(
    clock: ReplayClock,
    event: EventEnvelope,
) -> datetime | None:
    try:
        return clock.advance_to(event.occurred_at)
    except (TypeError, ValueError):
        return None
