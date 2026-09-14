"""Property tests for deterministic replay sorting."""

from __future__ import annotations

import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.replay import sort_replay_events
from pmrp.schemas.events import EventEnvelope
from pmrp.schemas.serialization import canonical_sha256

pytestmark = [pytest.mark.property, pytest.mark.replay]

_EVENT_SPECS: tuple[dict[str, object], ...] = (
    {"event_id": "evt_replay_sorter_0001", "exchange_sequence": 1},
    {"event_id": "evt_replay_sorter_0002", "exchange_sequence": 2},
    {"event_id": "evt_replay_sorter_0003", "source_partition": "partition_a"},
    {"event_id": "evt_replay_sorter_0004", "source_partition": "partition_b"},
    {"event_id": "evt_replay_sorter_0005", "received_at": "2026-07-28T15:00:01Z"},
    {"event_id": "evt_replay_sorter_0006", "occurred_at": "2026-07-28T15:00:01Z"},
)
_SPEC_INDICES = tuple(range(len(_EVENT_SPECS)))


@given(indices=st.permutations(_SPEC_INDICES))
def test_sort_replay_events_is_independent_of_input_order(indices: tuple[int, ...]) -> None:
    events = tuple(_event(**spec) for spec in _EVENT_SPECS)
    expected = sort_replay_events(events)
    shuffled = tuple(events[index] for index in indices)

    assert sort_replay_events(shuffled) == expected
    assert canonical_sha256(sort_replay_events(shuffled)) == canonical_sha256(expected)


def _event(
    event_id: object,
    *,
    occurred_at: object = "2026-07-28T15:00:00Z",
    received_at: object = "2026-07-28T15:00:00Z",
    exchange_sequence: object | None = None,
    source_partition: object | None = None,
) -> EventEnvelope:
    attributes: dict[str, object] = {}
    if exchange_sequence is not None:
        attributes["exchange_sequence"] = exchange_sequence
    if source_partition is not None:
        attributes["source_partition"] = source_partition
    return EventEnvelope.model_validate_json(
        json.dumps(
            {
                "account_id": None,
                "attributes": attributes,
                "causation_id": None,
                "correlation_id": "corr_replay_sorter",
                "event_id": event_id,
                "event_type": "market.trade_observed",
                "exchange": "kalshi",
                "market_id": "mkt_01j00000000000000000000000",
                "occurred_at": occurred_at,
                "order_id": None,
                "producer": "sorter_property_test",
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
