"""Tests for the idempotency SQLAlchemy row model."""

from __future__ import annotations

import pytest

from pmrp.storage.models import IdempotencyRecordRow, StorageBase


@pytest.mark.unit
def test_idempotency_record_row_mapping_matches_database_spec() -> None:
    table = IdempotencyRecordRow.__table__

    assert table.schema == "pmrp_core"
    assert table.name == "idempotency_records"
    assert [column.name for column in table.primary_key.columns] == [
        "subject_id",
        "operation",
        "idempotency_key",
    ]
    assert set(table.columns.keys()) == {
        "subject_id",
        "operation",
        "idempotency_key",
        "request_hash",
        "status",
        "response_status",
        "response_headers",
        "response_body",
        "created_at",
        "completed_at",
        "expires_at",
    }


@pytest.mark.unit
def test_idempotency_record_indexes_match_database_spec() -> None:
    assert {"ix_idempotency_records__expires"} <= {
        index.name for index in IdempotencyRecordRow.__table__.indexes
    }


@pytest.mark.unit
def test_idempotency_record_row_is_registered_in_storage_metadata() -> None:
    assert (
        StorageBase.metadata.tables["pmrp_core.idempotency_records"]
        is IdempotencyRecordRow.__table__
    )
