import json
from collections.abc import Mapping
from datetime import datetime

import pytest
from pydantic import ValidationError

from pmrp.schemas.commands import CommandEnvelope
from pmrp.schemas.identifiers import CommandId, EventId
from pmrp.schemas.serialization import canonical_json, canonical_sha256
from pmrp.schemas.versions import get_schema_model, get_schema_registration

pytestmark = pytest.mark.unit


def _command_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "command_id": "cmd_01j00000000000000000000000",
        "command_type": "order.place",
        "schema_version": 1,
        "issued_at": "2026-07-28T12:00:00Z",
        "issuer": "operator",
        "correlation_id": "corr_01j00000000000000000000000",
        "causation_id": "evt_01j00000000000000000000000",
        "trace_id": "trace-abc123",
        "idempotency_key": "idem-01j00000000000000000000000",
        "deadline_at": "2026-07-28T12:00:05Z",
        "priority": 10,
        "attributes": {"source": "unit_test"},
    }
    payload.update(overrides)
    return payload


def test_command_envelope_accepts_required_lineage_and_idempotency_fields() -> None:
    command = CommandEnvelope.model_validate(_command_payload())

    assert command.command_id == CommandId("cmd_01j00000000000000000000000")
    assert command.causation_id == EventId("evt_01j00000000000000000000000")
    assert command.idempotency_key == "idem-01j00000000000000000000000"


def test_command_envelope_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CommandEnvelope.model_validate(_command_payload(unexpected=True))


def test_command_envelope_rejects_invalid_command_type() -> None:
    with pytest.raises(ValidationError, match="String should match pattern"):
        CommandEnvelope.model_validate(_command_payload(command_type="PlaceOrder"))


def test_command_envelope_rejects_non_positive_schema_version() -> None:
    with pytest.raises(ValidationError, match="schema version must be positive"):
        CommandEnvelope.model_validate(_command_payload(schema_version=0))


def test_command_envelope_rejects_naive_issued_at() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        CommandEnvelope.model_validate(
            _command_payload(issued_at=datetime.fromisoformat("2026-07-28T12:00:00"))
        )


def test_command_envelope_rejects_empty_idempotency_key() -> None:
    with pytest.raises(ValidationError, match="at least 1 character"):
        CommandEnvelope.model_validate(_command_payload(idempotency_key=""))


def test_command_envelope_json_round_trip_preserves_fields() -> None:
    command = CommandEnvelope.model_validate_json(json.dumps(_command_payload()))

    assert command.command_type == "order.place"
    assert command.deadline_at is not None
    assert json.loads(command.model_dump_json())["deadline_at"] == "2026-07-28T12:00:05Z"


def test_command_envelope_attributes_are_deeply_immutable_after_validation() -> None:
    command = CommandEnvelope.model_validate(
        _command_payload(attributes={"source": "unit_test", "nested": {"levels": ["one"]}})
    )
    original_hash = canonical_sha256(command)
    nested_attributes = command.attributes["nested"]

    with pytest.raises(TypeError, match="does not support item assignment"):
        command.attributes["source"] = "changed"
    assert isinstance(nested_attributes, Mapping)
    with pytest.raises(TypeError, match="does not support item assignment"):
        nested_attributes["levels"] = ["changed"]

    assert canonical_sha256(command) == original_hash


def test_command_envelope_rejects_invalid_attribute_key() -> None:
    with pytest.raises(ValidationError, match="keys must be nonempty"):
        CommandEnvelope.model_validate(_command_payload(attributes={" source": "unit_test"}))


def test_command_envelope_canonical_hash_is_stable() -> None:
    command = CommandEnvelope.model_validate(_command_payload())

    assert canonical_json(command) == canonical_json(
        CommandEnvelope.model_validate(_command_payload())
    )
    assert canonical_sha256(command) == canonical_sha256(
        CommandEnvelope.model_validate(_command_payload())
    )


def test_command_envelope_registry_entry_exists() -> None:
    registration = get_schema_registration("command_envelope", 1)

    assert registration.model_path == "pmrp.schemas.commands.CommandEnvelope"
    assert get_schema_model("command_envelope", 1) is CommandEnvelope
