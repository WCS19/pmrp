"""Minimal deterministic replay engine."""

from __future__ import annotations

from collections.abc import Iterable

from pmrp.bus.protocol import EventBus
from pmrp.clock import ReplayClock
from pmrp.replay.clock import advance_replay_clock_to_event
from pmrp.replay.errors import ReplayEngineError
from pmrp.replay.loader import ReplayDataset
from pmrp.replay.sorter import REPLAY_ORDERING_POLICY_VERSION, sort_replay_events
from pmrp.schemas.events import EventEnvelope
from pmrp.schemas.replay import ReplayManifest, ReplaySession, ReplayState
from pmrp.schemas.serialization import canonical_sha256

REPLAY_ENGINE_VERSION = "replay_engine_v1"


class ReplayEngine:
    """Publish a validated replay dataset through injected runtime dependencies."""

    def __init__(
        self,
        *,
        clock: ReplayClock,
        event_bus: EventBus,
    ) -> None:
        self._clock = clock
        self._event_bus = event_bus

    async def run(self, dataset: ReplayDataset) -> ReplaySession:
        """Replay a dataset and return deterministic completed session metadata."""

        _validate_engine_inputs(dataset.manifest, self._clock)
        ordered_events = sort_replay_events(dataset.events)
        result_checksum = calculate_replay_result_checksum(
            manifest=dataset.manifest,
            ordered_events=ordered_events,
        )
        processed_events = 0
        for event in ordered_events:
            advance_replay_clock_to_event(
                self._clock,
                event,
                replay_session_id=dataset.manifest.replay_session_id,
            )
            published = await _try_publish_event(self._event_bus, event)
            if not published:
                raise ReplayEngineError(
                    "Replay event publication failed",
                    reason_code="replay_engine_event_publish_failed",
                    context={
                        "event_id": str(event.event_id),
                        "processed_events": str(processed_events),
                    },
                )
            processed_events += 1

        completed_at = self._clock.now()
        return ReplaySession(
            replay_session_id=dataset.manifest.replay_session_id,
            manifest=dataset.manifest,
            state=ReplayState.COMPLETED,
            current_time=completed_at,
            processed_events=processed_events,
            rejected_events=0,
            started_at=dataset.manifest.starts_at,
            completed_at=completed_at,
            result_checksum=result_checksum,
        )


def calculate_replay_result_checksum(
    *,
    manifest: ReplayManifest,
    ordered_events: Iterable[EventEnvelope],
) -> str:
    """Hash deterministic baseline replay output for an ordered event stream."""

    event_hashes = tuple(canonical_sha256(event) for event in ordered_events)
    return canonical_sha256(
        {
            "dataset_checksum": manifest.dataset_checksum,
            "dataset_id": manifest.dataset_id,
            "engine_version": REPLAY_ENGINE_VERSION,
            "event_hashes": event_hashes,
            "event_ordering_policy_version": manifest.event_ordering_policy_version,
            "processed_events": len(event_hashes),
            "replay_session_id": str(manifest.replay_session_id),
        }
    )


def _validate_engine_inputs(manifest: ReplayManifest, clock: ReplayClock) -> None:
    if manifest.event_ordering_policy_version != REPLAY_ORDERING_POLICY_VERSION:
        raise ReplayEngineError(
            "Replay manifest ordering policy is not supported by this replay engine",
            reason_code="replay_engine_ordering_policy_unsupported",
            context={
                "expected_policy": REPLAY_ORDERING_POLICY_VERSION,
                "actual_policy": manifest.event_ordering_policy_version,
            },
        )
    if clock.starts_at != manifest.starts_at or clock.ends_at != manifest.ends_at:
        raise ReplayEngineError(
            "Replay clock window must match replay manifest window",
            reason_code="replay_engine_clock_window_mismatch",
            context={
                "replay_session_id": str(manifest.replay_session_id),
                "dataset_id": manifest.dataset_id,
            },
        )


async def _try_publish_event(event_bus: EventBus, event: EventEnvelope) -> bool:
    try:
        await event_bus.publish(event)
    except Exception:
        return False
    return True
