"""Replay package clock helper tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pmrp.clock import ReplayClock
from pmrp.replay import (
    ReplayClockError,
    advance_replay_clock_to_event,
    build_replay_clock,
    load_replay_manifest,
)
from pmrp.schemas.events import EventEnvelope

pytestmark = [pytest.mark.replay, pytest.mark.unit]

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "replay" / "basic_market"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"


def test_build_replay_clock_uses_manifest_window() -> None:
    manifest = load_replay_manifest(MANIFEST_PATH)
    clock = build_replay_clock(manifest)

    assert isinstance(clock, ReplayClock)
    assert clock.starts_at == datetime(2026, 7, 28, 15, 0, tzinfo=UTC)
    assert clock.ends_at == datetime(2026, 7, 28, 16, 0, tzinfo=UTC)
    assert clock.now() == clock.starts_at


def test_build_replay_clock_accepts_normalized_current_time() -> None:
    manifest = load_replay_manifest(MANIFEST_PATH)
    clock = build_replay_clock(
        manifest,
        current_time=datetime.fromisoformat("2026-07-28T09:30:00-05:30"),
    )

    assert clock.now() == datetime(2026, 7, 28, 15, 0, tzinfo=UTC)


def test_build_replay_clock_wraps_invalid_initial_time_safely() -> None:
    manifest = load_replay_manifest(MANIFEST_PATH)

    with pytest.raises(ReplayClockError) as exc_info:
        build_replay_clock(
            manifest,
            current_time=datetime(2026, 7, 28, 16, 0, 1, tzinfo=UTC),
        )

    assert str(exc_info.value) == "Replay clock could not be initialized from manifest"
    assert exc_info.value.reason_code == "replay_clock_initialization_failed"
    assert exc_info.value.context["replay_session_id"] == manifest.replay_session_id
    assert exc_info.value.context["dataset_id"] == manifest.dataset_id
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_advance_replay_clock_to_event_moves_to_event_occurred_time() -> None:
    manifest = load_replay_manifest(MANIFEST_PATH)
    clock = build_replay_clock(manifest)
    event = _event("evt_replay_clock_0001", occurred_at="2026-07-28T15:00:10Z")

    assert advance_replay_clock_to_event(
        clock,
        event,
        replay_session_id=manifest.replay_session_id,
    ) == datetime(
        2026,
        7,
        28,
        15,
        0,
        10,
        tzinfo=UTC,
    )
    assert clock.now() == datetime(2026, 7, 28, 15, 0, 10, tzinfo=UTC)


def test_advance_replay_clock_to_event_allows_equal_timestamp() -> None:
    manifest = load_replay_manifest(MANIFEST_PATH)
    clock = build_replay_clock(manifest)
    event = _event("evt_replay_clock_0001", occurred_at="2026-07-28T15:00:00Z")

    assert advance_replay_clock_to_event(clock, event) == clock.starts_at


def test_advance_replay_clock_to_event_rejects_missing_replay_session_id_safely() -> None:
    manifest = load_replay_manifest(MANIFEST_PATH)
    clock = build_replay_clock(manifest)
    event = _event("evt_replay_clock_0001", replay_session_id=None)

    with pytest.raises(ReplayClockError) as exc_info:
        advance_replay_clock_to_event(clock, event)

    assert str(exc_info.value) == (
        "Replay event must include replay_session_id before clock advancement"
    )
    assert exc_info.value.reason_code == "replay_clock_event_session_missing"
    assert exc_info.value.context["event_id"] == "evt_replay_clock_0001"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_advance_replay_clock_to_event_rejects_wrong_replay_session_id_safely() -> None:
    manifest = load_replay_manifest(MANIFEST_PATH)
    clock = build_replay_clock(manifest)
    event = _event(
        "evt_replay_clock_0001",
        replay_session_id="rpl_01j11111111111111111111111",
    )

    with pytest.raises(ReplayClockError) as exc_info:
        advance_replay_clock_to_event(
            clock,
            event,
            replay_session_id=manifest.replay_session_id,
        )

    assert str(exc_info.value) == (
        "Replay event replay_session_id does not match clock replay_session_id"
    )
    assert exc_info.value.reason_code == "replay_clock_event_session_mismatch"
    assert exc_info.value.context["event_id"] == "evt_replay_clock_0001"
    assert exc_info.value.context["expected_replay_session_id"] == manifest.replay_session_id
    assert exc_info.value.context["actual_replay_session_id"] == "rpl_01j11111111111111111111111"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_advance_replay_clock_to_event_rejects_backward_time_safely() -> None:
    manifest = load_replay_manifest(MANIFEST_PATH)
    clock = build_replay_clock(
        manifest,
        current_time=datetime(2026, 7, 28, 15, 1, tzinfo=UTC),
    )
    event = _event("evt_replay_clock_0001", occurred_at="2026-07-28T15:00:59Z")

    with pytest.raises(ReplayClockError) as exc_info:
        advance_replay_clock_to_event(clock, event)

    assert str(exc_info.value) == "Replay event occurrence time cannot move clock backward"
    assert exc_info.value.reason_code == "replay_clock_event_time_reversed"
    assert exc_info.value.context["event_id"] == "evt_replay_clock_0001"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_advance_replay_clock_to_event_rejects_event_outside_clock_window_safely() -> None:
    manifest = load_replay_manifest(MANIFEST_PATH)
    clock = build_replay_clock(manifest)
    event = _event("evt_replay_clock_0001", occurred_at="2026-07-28T16:00:01Z")

    with pytest.raises(ReplayClockError) as exc_info:
        advance_replay_clock_to_event(clock, event)

    assert str(exc_info.value) == (
        "Replay event occurrence time is outside the replay clock window"
    )
    assert exc_info.value.reason_code == "replay_clock_event_out_of_window"
    assert exc_info.value.context["event_id"] == "evt_replay_clock_0001"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_replay_clock_helpers_do_not_use_wall_clock_network_or_live_boundaries() -> None:
    source = Path(__file__).resolve().parents[2] / "src" / "pmrp" / "replay" / "clock.py"
    text = source.read_text(encoding="utf-8")

    assert "datetime.now" not in text
    assert "time.time" not in text
    assert "pmrp.adapters" not in text
    assert "pmrp.execution" not in text
    assert "sqlalchemy" not in text
    assert "asyncpg" not in text
    assert "httpx" not in text
    assert "requests" not in text


def _event(
    event_id: str,
    *,
    occurred_at: str = "2026-07-28T15:00:00Z",
    replay_session_id: str | None = "rpl_01j00000000000000000000000",
) -> EventEnvelope:
    return EventEnvelope.model_validate_json(
        json.dumps(
            {
                "account_id": None,
                "attributes": {},
                "causation_id": None,
                "correlation_id": "corr_replay_clock",
                "event_id": event_id,
                "event_type": "market.trade_observed",
                "exchange": "kalshi",
                "market_id": "mkt_01j00000000000000000000000",
                "occurred_at": occurred_at,
                "order_id": None,
                "producer": "clock_test",
                "published_at": occurred_at,
                "quality_flags": [],
                "received_at": occurred_at,
                "replay_session_id": replay_session_id,
                "schema_version": 1,
                "simulation_session_id": None,
                "strategy_id": None,
                "trace_id": "trace_replay_clock",
            }
        )
    )
