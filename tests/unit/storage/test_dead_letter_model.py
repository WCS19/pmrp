"""Tests for the dead-letter SQLAlchemy row model."""

from __future__ import annotations

import pytest

from pmrp.storage.models import DeadLetterRecordRow, StorageBase


@pytest.mark.unit
def test_dead_letter_record_row_mapping_matches_database_spec() -> None:
    table = DeadLetterRecordRow.__table__

    assert table.schema == "pmrp_ops"
    assert table.name == "dead_letter_records"
    assert [column.name for column in table.primary_key.columns] == ["dead_letter_id"]
    assert set(table.columns.keys()) == {
        "dead_letter_id",
        "source_event_id",
        "source_command_id",
        "consumer_name",
        "failure_category",
        "exception_type",
        "exception_message",
        "first_failed_at",
        "last_failed_at",
        "retry_count",
        "payload_reference",
        "replayable",
        "resolved_at",
        "resolution_note",
        "created_at",
    }


@pytest.mark.unit
def test_dead_letter_record_unresolved_index_matches_database_spec() -> None:
    pending_index = next(
        index
        for index in DeadLetterRecordRow.__table__.indexes
        if index.name == "ix_dead_letter_records__unresolved"
    )

    assert [column.name for column in pending_index.columns] == ["last_failed_at"]
    assert str(pending_index.dialect_options["postgresql"]["where"]) == ("resolved_at IS NULL")


@pytest.mark.unit
def test_dead_letter_record_row_is_registered_in_storage_metadata() -> None:
    assert (
        StorageBase.metadata.tables["pmrp_ops.dead_letter_records"] is DeadLetterRecordRow.__table__
    )
