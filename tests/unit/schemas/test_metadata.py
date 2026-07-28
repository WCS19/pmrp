from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from pmrp.schemas.metadata import AuditMetadata, SourceMetadata, VersionMetadata

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
