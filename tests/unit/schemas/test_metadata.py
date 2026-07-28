from collections.abc import Mapping
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from pmrp.schemas.metadata import AuditMetadata, FlexibleMetadata, SourceMetadata, VersionMetadata
from pmrp.schemas.serialization import canonical_json, canonical_sha256

pytestmark = pytest.mark.unit


def test_source_metadata_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SourceMetadata(producer="normalizer", source_type="adapter", extra_value=True)


def test_version_metadata_requires_positive_schema_version() -> None:
    with pytest.raises(ValidationError, match="schema version must be positive"):
        VersionMetadata(schema_version=0)


def test_audit_metadata_uses_utc_datetime_validation() -> None:
    metadata = AuditMetadata(
        created_at=datetime(2026, 7, 28, 12, 0, tzinfo=UTC),
        created_by="tester",
    )

    assert metadata.created_at == datetime(2026, 7, 28, 12, 0, tzinfo=UTC)


def test_flexible_metadata_values_are_deeply_immutable_after_validation() -> None:
    metadata = FlexibleMetadata.model_validate(
        {"values": {"source": "unit_test", "nested": {"levels": ["one"]}}}
    )
    original_hash = canonical_sha256(metadata)
    nested_values = metadata.values["nested"]

    with pytest.raises(TypeError, match="does not support item assignment"):
        metadata.values["source"] = "changed"
    assert isinstance(nested_values, Mapping)
    with pytest.raises(TypeError, match="does not support item assignment"):
        nested_values["levels"] = ["changed"]

    assert canonical_sha256(metadata) == original_hash


def test_flexible_metadata_rejects_invalid_value_key() -> None:
    with pytest.raises(ValidationError, match="keys must be nonempty"):
        FlexibleMetadata.model_validate({"values": {" source": "unit_test"}})


def test_flexible_metadata_json_round_trip_preserves_values() -> None:
    metadata = FlexibleMetadata.model_validate({"values": {"tags": ["one", "two"]}})

    assert FlexibleMetadata.model_validate_json(canonical_json(metadata)) == metadata
