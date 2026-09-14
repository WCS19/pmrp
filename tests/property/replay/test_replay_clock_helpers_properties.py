"""Property tests for replay clock helpers."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.replay import advance_replay_clock_to_event, build_replay_clock, load_replay_manifest
from pmrp.schemas.events import EventEnvelope
from pmrp.schemas.time import format_utc_datetime

pytestmark = [pytest.mark.property, pytest.mark.replay]

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "replay" / "basic_market"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"


@given(offset_seconds=st.integers(min_value=0, max_value=3_600))
def test_advance_replay_clock_to_generated_event_offsets(offset_seconds: int) -> None:
    manifest = load_replay_manifest(MANIFEST_PATH)
    clock = build_replay_clock(manifest)
    occurred_at = manifest.starts_at + timedelta(seconds=offset_seconds)
    event = _event(format_utc_datetime(occurred_at))

    assert (
        advance_replay_clock_to_event(
            clock,
            event,
            replay_session_id=manifest.replay_session_id,
        )
        == occurred_at
    )
    assert clock.now() == occurred_at


def _event(occurred_at: str) -> EventEnvelope:
    return EventEnvelope.model_validate_json(
        json.dumps(
            {
                "account_id": None,
                "attributes": {},
                "causation_id": None,
                "correlation_id": "corr_replay_clock",
                "event_id": "evt_replay_clock_property",
                "event_type": "market.trade_observed",
                "exchange": "kalshi",
                "market_id": "mkt_01j00000000000000000000000",
                "occurred_at": occurred_at,
                "order_id": None,
                "producer": "clock_property_test",
                "published_at": occurred_at,
                "quality_flags": [],
                "received_at": occurred_at,
                "replay_session_id": "rpl_01j00000000000000000000000",
                "schema_version": 1,
                "simulation_session_id": None,
                "strategy_id": None,
                "trace_id": "trace_replay_clock",
            }
        )
    )
