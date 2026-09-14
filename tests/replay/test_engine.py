"""Deterministic replay engine tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pmrp.clock import ReplayClock
from pmrp.replay import (
    REPLAY_ENGINE_VERSION,
    ReplayDataset,
    ReplayEngine,
    ReplayEngineError,
    build_replay_clock,
    calculate_replay_result_checksum,
    load_replay_events_jsonl,
    load_replay_manifest,
    sort_replay_events,
)
from pmrp.schemas.events import EventEnvelope
from pmrp.schemas.replay import ReplayManifest, ReplayState

pytestmark = [pytest.mark.replay, pytest.mark.unit]

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "replay" / "basic_market"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"
EVENTS_PATH = FIXTURE_ROOT / "events.jsonl"


def test_replay_engine_version_is_stable() -> None:
    assert REPLAY_ENGINE_VERSION == "replay_engine_v1"


async def test_replay_engine_publishes_sorted_events_and_returns_completed_session() -> None:
    manifest = load_replay_manifest(MANIFEST_PATH)
    fixture_events = load_replay_events_jsonl(EVENTS_PATH)
    dataset = ReplayDataset(
        manifest=manifest,
        events=tuple(reversed(fixture_events)),
        dataset_checksum=manifest.dataset_checksum,
    )
    event_bus = RecordingEventBus()
    engine = ReplayEngine(clock=build_replay_clock(manifest), event_bus=event_bus)

    session = await engine.run(dataset)

    assert [event.event_id for event in event_bus.events] == ["evt_replay_0001", "evt_replay_0002"]
    assert session.replay_session_id == manifest.replay_session_id
    assert session.state is ReplayState.COMPLETED
    assert session.current_time == fixture_events[-1].occurred_at
    assert session.started_at == manifest.starts_at
    assert session.completed_at == fixture_events[-1].occurred_at
    assert session.processed_events == 2
    assert session.rejected_events == 0
    assert session.result_checksum == calculate_replay_result_checksum(
        manifest=manifest,
        ordered_events=sort_replay_events(dataset.events),
    )


async def test_replay_engine_result_checksum_is_stable_across_input_order() -> None:
    manifest = load_replay_manifest(MANIFEST_PATH)
    events = load_replay_events_jsonl(EVENTS_PATH)
    original_dataset = ReplayDataset(
        manifest=manifest,
        events=events,
        dataset_checksum=manifest.dataset_checksum,
    )
    reversed_dataset = ReplayDataset(
        manifest=manifest,
        events=tuple(reversed(events)),
        dataset_checksum=manifest.dataset_checksum,
    )

    original_session = await ReplayEngine(
        clock=build_replay_clock(manifest),
        event_bus=RecordingEventBus(),
    ).run(original_dataset)
    reversed_session = await ReplayEngine(
        clock=build_replay_clock(manifest),
        event_bus=RecordingEventBus(),
    ).run(reversed_dataset)

    assert original_session.result_checksum == reversed_session.result_checksum
    assert original_session.processed_events == reversed_session.processed_events == 2


async def test_replay_engine_rejects_unsupported_ordering_policy_safely() -> None:
    manifest = _manifest_with(event_ordering_policy_version="unsupported-policy")
    dataset = ReplayDataset(
        manifest=manifest,
        events=load_replay_events_jsonl(EVENTS_PATH),
        dataset_checksum=manifest.dataset_checksum,
    )
    engine = ReplayEngine(clock=build_replay_clock(manifest), event_bus=RecordingEventBus())

    with pytest.raises(ReplayEngineError) as exc_info:
        await engine.run(dataset)

    assert str(exc_info.value) == (
        "Replay manifest ordering policy is not supported by this replay engine"
    )
    assert exc_info.value.reason_code == "replay_engine_ordering_policy_unsupported"
    assert exc_info.value.context["expected_policy"] == "occurred-sequence-received-v1"
    assert exc_info.value.context["actual_policy"] == "unsupported-policy"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


async def test_replay_engine_rejects_clock_window_mismatch_safely() -> None:
    manifest = load_replay_manifest(MANIFEST_PATH)
    dataset = ReplayDataset(
        manifest=manifest,
        events=load_replay_events_jsonl(EVENTS_PATH),
        dataset_checksum=manifest.dataset_checksum,
    )
    mismatched_clock = ReplayClock(
        starts_at=manifest.starts_at,
        ends_at=manifest.ends_at.replace(hour=17),
    )
    engine = ReplayEngine(clock=mismatched_clock, event_bus=RecordingEventBus())

    with pytest.raises(ReplayEngineError) as exc_info:
        await engine.run(dataset)

    assert str(exc_info.value) == "Replay clock window must match replay manifest window"
    assert exc_info.value.reason_code == "replay_engine_clock_window_mismatch"
    assert exc_info.value.context["replay_session_id"] == manifest.replay_session_id
    assert exc_info.value.context["dataset_id"] == manifest.dataset_id
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


async def test_replay_engine_wraps_event_publish_failure_safely() -> None:
    manifest = load_replay_manifest(MANIFEST_PATH)
    dataset = ReplayDataset(
        manifest=manifest,
        events=load_replay_events_jsonl(EVENTS_PATH),
        dataset_checksum=manifest.dataset_checksum,
    )
    engine = ReplayEngine(
        clock=build_replay_clock(manifest),
        event_bus=FailingEventBus(),
    )

    with pytest.raises(ReplayEngineError) as exc_info:
        await engine.run(dataset)

    assert str(exc_info.value) == "Replay event publication failed"
    assert exc_info.value.reason_code == "replay_engine_event_publish_failed"
    assert exc_info.value.context["event_id"] == "evt_replay_0001"
    assert exc_info.value.context["processed_events"] == "0"
    assert "raw_payload_sentinel" not in str(exc_info.value)
    assert "raw_payload_sentinel" not in exc_info.value.context.values()
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_replay_engine_does_not_use_wall_clock_network_storage_or_live_boundaries() -> None:
    source = Path(__file__).resolve().parents[2] / "src" / "pmrp" / "replay" / "engine.py"
    text = source.read_text(encoding="utf-8")

    assert "datetime.now" not in text
    assert "time.time" not in text
    assert "pmrp.adapters" not in text
    assert "pmrp.execution" not in text
    assert "sqlalchemy" not in text
    assert "asyncpg" not in text
    assert "httpx" not in text
    assert "requests" not in text


class RecordingEventBus:
    def __init__(self) -> None:
        self.events: list[EventEnvelope] = []

    async def publish(self, event: object, *, partition_key: str | None = None) -> None:
        del partition_key
        if not isinstance(event, EventEnvelope):
            msg = "recording bus only accepts EventEnvelope"
            raise TypeError(msg)
        self.events.append(event)

    def subscribe(
        self,
        event_type: type[Any],
        *,
        consumer_name: str,
        partition_key: str | None = None,
        queue_size: int | None = None,
    ) -> object:
        del event_type, consumer_name, partition_key, queue_size
        msg = "recording bus does not implement subscriptions"
        raise NotImplementedError(msg)

    async def close(self) -> None:
        return None


class FailingEventBus(RecordingEventBus):
    async def publish(self, event: object, *, partition_key: str | None = None) -> None:
        del event, partition_key
        msg = "raw_payload_sentinel"
        raise RuntimeError(msg)


def _manifest_with(**overrides: object) -> ReplayManifest:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    payload.update(overrides)
    return ReplayManifest.model_validate_json(json.dumps(payload))
