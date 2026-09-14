"""Property tests for deterministic replay engine execution."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.replay import ReplayDataset, ReplayEngine, build_replay_clock, load_replay_manifest
from pmrp.schemas.events import EventEnvelope
from pmrp.schemas.replay import ReplayManifest

pytestmark = [pytest.mark.property, pytest.mark.replay]

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "replay" / "basic_market"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"
_EVENT_SPECS: tuple[tuple[str, str, int | None], ...] = (
    ("evt_replay_engine_0001", "2026-07-28T15:00:00Z", 1),
    ("evt_replay_engine_0002", "2026-07-28T15:00:00Z", 2),
    ("evt_replay_engine_0003", "2026-07-28T15:00:01Z", None),
    ("evt_replay_engine_0004", "2026-07-28T15:00:02Z", None),
)
_SPEC_INDICES = tuple(range(len(_EVENT_SPECS)))


@given(indices=st.permutations(_SPEC_INDICES))
def test_replay_engine_result_is_independent_of_input_order(indices: tuple[int, ...]) -> None:
    expected_session, expected_ids = asyncio.run(_run_engine(_SPEC_INDICES))
    actual_session, actual_ids = asyncio.run(_run_engine(indices))

    assert actual_ids == expected_ids
    assert actual_session.result_checksum == expected_session.result_checksum
    assert actual_session.processed_events == len(_EVENT_SPECS)


async def _run_engine(indices: tuple[int, ...]) -> tuple[object, tuple[str, ...]]:
    manifest = load_replay_manifest(MANIFEST_PATH)
    events = tuple(_event(manifest, *_EVENT_SPECS[index]) for index in indices)
    dataset = ReplayDataset(
        manifest=manifest,
        events=events,
        dataset_checksum=manifest.dataset_checksum,
    )
    event_bus = RecordingEventBus()
    session = await ReplayEngine(
        clock=build_replay_clock(manifest),
        event_bus=event_bus,
    ).run(dataset)
    return session, tuple(str(event.event_id) for event in event_bus.events)


def _event(
    manifest: ReplayManifest,
    event_id: str,
    occurred_at: str,
    exchange_sequence: int | None,
) -> EventEnvelope:
    attributes: dict[str, object] = {"source_partition": "engine_property"}
    if exchange_sequence is not None:
        attributes["exchange_sequence"] = exchange_sequence
    return EventEnvelope.model_validate_json(
        json.dumps(
            {
                "account_id": None,
                "attributes": attributes,
                "causation_id": None,
                "correlation_id": "corr_replay_engine",
                "event_id": event_id,
                "event_type": "market.trade_observed",
                "exchange": "kalshi",
                "market_id": "mkt_01j00000000000000000000000",
                "occurred_at": occurred_at,
                "order_id": None,
                "producer": "engine_property_test",
                "published_at": occurred_at,
                "quality_flags": [],
                "received_at": occurred_at,
                "replay_session_id": manifest.replay_session_id,
                "schema_version": 1,
                "simulation_session_id": None,
                "strategy_id": None,
                "trace_id": "trace_replay_engine",
            }
        )
    )


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
