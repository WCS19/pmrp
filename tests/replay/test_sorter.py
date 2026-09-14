"""Deterministic replay event sorter tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pmrp.replay import (
    REPLAY_ORDERING_POLICY_VERSION,
    ReplayOrderingError,
    replay_event_ordering_key,
    sort_replay_events,
)
from pmrp.schemas.events import EventEnvelope

pytestmark = [pytest.mark.replay, pytest.mark.unit]


def test_replay_ordering_policy_version_is_stable() -> None:
    assert REPLAY_ORDERING_POLICY_VERSION == "occurred-sequence-received-v1"


def test_sort_replay_events_applies_documented_tie_break_order() -> None:
    events = (
        _event("evt_replay_sorter_0006", occurred_at="2026-07-28T15:00:01Z"),
        _event(
            "evt_replay_sorter_0004",
            received_at="2026-07-28T15:00:00Z",
            source_partition="partition_b",
        ),
        _event(
            "evt_replay_sorter_0002",
            received_at="2026-07-28T15:00:00Z",
            exchange_sequence=2,
            source_partition="partition_a",
        ),
        _event(
            "evt_replay_sorter_0005",
            received_at="2026-07-28T15:00:00Z",
            source_partition="partition_a",
        ),
        _event(
            "evt_replay_sorter_0003",
            received_at="2026-07-28T15:00:01Z",
            source_partition="partition_a",
        ),
        _event(
            "evt_replay_sorter_0001",
            received_at="2026-07-28T15:00:59Z",
            exchange_sequence=1,
            source_partition="partition_z",
        ),
    )

    assert [event.event_id for event in sort_replay_events(events)] == [
        "evt_replay_sorter_0001",
        "evt_replay_sorter_0002",
        "evt_replay_sorter_0005",
        "evt_replay_sorter_0004",
        "evt_replay_sorter_0003",
        "evt_replay_sorter_0006",
    ]


def test_missing_exchange_sequence_sorts_after_available_sequence() -> None:
    sequenced = _event("evt_replay_sorter_0001", exchange_sequence=100)
    unsequenced = _event(
        "evt_replay_sorter_0002",
        received_at="2026-07-28T15:00:00Z",
        source_partition="partition_a",
    )

    assert sort_replay_events((unsequenced, sequenced)) == (sequenced, unsequenced)


def test_source_partition_and_event_id_are_final_tie_breakers() -> None:
    events = (
        _event("evt_replay_sorter_0003", source_partition="partition_b"),
        _event("evt_replay_sorter_0002", source_partition="partition_a"),
        _event("evt_replay_sorter_0001", source_partition="partition_a"),
    )

    assert [event.event_id for event in sort_replay_events(events)] == [
        "evt_replay_sorter_0001",
        "evt_replay_sorter_0002",
        "evt_replay_sorter_0003",
    ]


@pytest.mark.parametrize("exchange_sequence", [-1, True, "1"])
def test_ordering_key_rejects_invalid_exchange_sequence_safely(
    exchange_sequence: object,
) -> None:
    event = _event(
        "evt_replay_sorter_0001",
        attributes={"exchange_sequence": exchange_sequence},
    )

    with pytest.raises(ReplayOrderingError) as exc_info:
        replay_event_ordering_key(event)

    assert str(exc_info.value) == (
        "Replay event exchange sequence must be a nonnegative integer when present"
    )
    assert exc_info.value.reason_code == "replay_ordering_sequence_invalid"
    assert exc_info.value.context["event_id"] == "evt_replay_sorter_0001"
    assert exc_info.value.context["attribute"] == "exchange_sequence"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


@pytest.mark.parametrize("source_partition", ["", " partition_a", 1])
def test_ordering_key_rejects_invalid_source_partition_safely(
    source_partition: object,
) -> None:
    event = _event(
        "evt_replay_sorter_0001",
        attributes={"source_partition": source_partition},
    )

    with pytest.raises(ReplayOrderingError) as exc_info:
        replay_event_ordering_key(event)

    assert str(exc_info.value) == (
        "Replay event source partition must be a stable string when present"
    )
    assert exc_info.value.reason_code == "replay_ordering_partition_invalid"
    assert exc_info.value.context["event_id"] == "evt_replay_sorter_0001"
    assert exc_info.value.context["attribute"] == "source_partition"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_replay_sorter_does_not_use_wall_clock_network_or_live_boundaries() -> None:
    source = Path(__file__).resolve().parents[2] / "src" / "pmrp" / "replay" / "sorter.py"
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
    received_at: str = "2026-07-28T15:00:00Z",
    exchange_sequence: int | None = None,
    source_partition: str | None = None,
    attributes: dict[str, object] | None = None,
) -> EventEnvelope:
    event_attributes = dict(attributes or {})
    if exchange_sequence is not None:
        event_attributes["exchange_sequence"] = exchange_sequence
    if source_partition is not None:
        event_attributes["source_partition"] = source_partition
    return EventEnvelope.model_validate_json(
        json.dumps(
            {
                "account_id": None,
                "attributes": event_attributes,
                "causation_id": None,
                "correlation_id": "corr_replay_sorter",
                "event_id": event_id,
                "event_type": "market.trade_observed",
                "exchange": "kalshi",
                "market_id": "mkt_01j00000000000000000000000",
                "occurred_at": occurred_at,
                "order_id": None,
                "producer": "sorter_test",
                "published_at": received_at,
                "quality_flags": [],
                "received_at": received_at,
                "replay_session_id": "rpl_01j00000000000000000000000",
                "schema_version": 1,
                "simulation_session_id": None,
                "strategy_id": None,
                "trace_id": "trace_replay_sorter",
            }
        )
    )
