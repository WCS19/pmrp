import json
from collections.abc import Mapping
from datetime import datetime

import pytest
from pydantic import ValidationError

from pmrp.schemas.enums import DataQualityFlag
from pmrp.schemas.events import EventEnvelope
from pmrp.schemas.identifiers import CausationId, CommandId, EventId
from pmrp.schemas.serialization import canonical_json, canonical_sha256
from pmrp.schemas.versions import get_schema_model, get_schema_registration

pytestmark = pytest.mark.unit


def _event_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "event_id": "evt_01j00000000000000000000000",
        "event_type": "order.created",
        "schema_version": 1,
        "occurred_at": "2026-07-28T12:00:00Z",
        "received_at": "2026-07-28T12:00:00.100000Z",
        "published_at": "2026-07-28T12:00:00.200000Z",
        "producer": "execution",
        "exchange": "kalshi",
        "market_id": "mkt_01j00000000000000000000000",
        "account_id": "acct_shadow",
        "strategy_id": "strat_example",
        "order_id": "ord_01j00000000000000000000000",
        "correlation_id": "corr_01j00000000000000000000000",
        "causation_id": "evt_01j00000000000000000000001",
        "trace_id": "trace-abc123",
        "replay_session_id": None,
        "simulation_session_id": None,
        "quality_flags": (DataQualityFlag.REPLAYED,),
        "attributes": {"source": "unit_test"},
    }
    payload.update(overrides)
    return payload


def test_event_envelope_accepts_required_lineage_fields() -> None:
    event = EventEnvelope.model_validate(_event_payload())

    assert event.event_id == EventId("evt_01j00000000000000000000000")
    assert event.correlation_id == "corr_01j00000000000000000000000"
    assert event.causation_id == EventId("evt_01j00000000000000000000001")
    assert event.quality_flags == (DataQualityFlag.REPLAYED,)


def test_event_envelope_accepts_command_causation_reference() -> None:
    event = EventEnvelope.model_validate(
        _event_payload(causation_id="cmd_01j00000000000000000000000")
    )

    assert event.causation_id == CommandId("cmd_01j00000000000000000000000")


def test_event_envelope_accepts_explicit_causation_identifier() -> None:
    event = EventEnvelope.model_validate(
        _event_payload(causation_id="cause_01j00000000000000000000000")
    )

    assert event.causation_id == CausationId("cause_01j00000000000000000000000")


def test_event_envelope_rejects_unsupported_causation_prefix() -> None:
    with pytest.raises(ValidationError, match="must start"):
        EventEnvelope.model_validate(_event_payload(causation_id="risk_01j"))


def test_event_envelope_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        EventEnvelope.model_validate(_event_payload(unexpected=True))


def test_event_envelope_rejects_invalid_event_type() -> None:
    with pytest.raises(ValidationError, match="String should match pattern"):
        EventEnvelope.model_validate(_event_payload(event_type="OrderCreated"))


def test_event_envelope_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        EventEnvelope.model_validate(
            _event_payload(occurred_at=datetime.fromisoformat("2026-07-28T12:00:00"))
        )


def test_event_envelope_serializes_datetimes_enums_and_ids() -> None:
    event = EventEnvelope.model_validate(_event_payload())

    serialized = json.loads(event.model_dump_json())

    assert serialized["occurred_at"] == "2026-07-28T12:00:00Z"
    assert serialized["quality_flags"] == ["replayed"]
    assert serialized["event_id"] == "evt_01j00000000000000000000000"


def test_event_envelope_attributes_are_deeply_immutable_after_validation() -> None:
    event = EventEnvelope.model_validate(
        _event_payload(attributes={"source": "unit_test", "nested": {"levels": ["one"]}})
    )
    original_hash = canonical_sha256(event)
    nested_attributes = event.attributes["nested"]

    with pytest.raises(TypeError, match="does not support item assignment"):
        event.attributes["source"] = "changed"
    assert isinstance(nested_attributes, Mapping)
    with pytest.raises(TypeError, match="does not support item assignment"):
        nested_attributes["levels"] = ["changed"]

    assert canonical_sha256(event) == original_hash


def test_event_envelope_rejects_invalid_attribute_key() -> None:
    with pytest.raises(ValidationError, match="keys must be nonempty"):
        EventEnvelope.model_validate(_event_payload(attributes={" source": "unit_test"}))


def test_event_envelope_json_round_trip_accepts_quality_flag_array() -> None:
    event = EventEnvelope.model_validate_json(json.dumps(_event_payload()))

    assert event.quality_flags == (DataQualityFlag.REPLAYED,)


def test_event_envelope_canonical_hash_is_stable() -> None:
    event = EventEnvelope.model_validate(_event_payload())

    assert canonical_json(event) == canonical_json(EventEnvelope.model_validate(_event_payload()))
    assert canonical_sha256(event) == canonical_sha256(
        EventEnvelope.model_validate(_event_payload())
    )


def test_event_envelope_registry_entry_exists() -> None:
    registration = get_schema_registration("event_envelope", 1)

    assert registration.model_path == "pmrp.schemas.events.EventEnvelope"
    assert get_schema_model("event_envelope", 1) is EventEnvelope
