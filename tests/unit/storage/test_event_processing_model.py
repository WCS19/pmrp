"""Tests for processed-event and outbox SQLAlchemy row models."""

from __future__ import annotations

import pytest

from pmrp.storage.models import OutboxMessageRow, ProcessedEventRow, StorageBase


@pytest.mark.unit
def test_processed_event_row_mapping_matches_database_spec() -> None:
    table = ProcessedEventRow.__table__

    assert table.schema == "pmrp_event"
    assert table.name == "processed_events"
    assert [column.name for column in table.primary_key.columns] == [
        "consumer_name",
        "event_id",
    ]
    assert set(table.columns.keys()) == {
        "consumer_name",
        "event_id",
        "processed_at",
        "processing_version",
        "result_hash",
    }


@pytest.mark.unit
def test_processed_event_indexes_match_database_spec() -> None:
    assert {"ix_processed_events__time"} <= {
        index.name for index in ProcessedEventRow.__table__.indexes
    }


@pytest.mark.unit
def test_outbox_message_row_mapping_matches_database_spec() -> None:
    table = OutboxMessageRow.__table__

    assert table.schema == "pmrp_event"
    assert table.name == "outbox_messages"
    assert [column.name for column in table.primary_key.columns] == ["outbox_id"]
    assert set(table.columns.keys()) == {
        "outbox_id",
        "event_id",
        "topic",
        "partition_key",
        "payload",
        "created_at",
        "available_at",
        "published_at",
        "publish_attempts",
        "last_error",
    }


@pytest.mark.unit
def test_outbox_message_constraints_and_indexes_match_database_spec() -> None:
    table = OutboxMessageRow.__table__

    assert "uq_outbox_messages__event_id_topic" in {
        constraint.name for constraint in table.constraints
    }
    pending_index = next(
        index for index in table.indexes if index.name == "ix_outbox_messages__pending"
    )
    assert [column.name for column in pending_index.columns] == ["available_at", "outbox_id"]
    assert str(pending_index.dialect_options["postgresql"]["where"]) == ("published_at IS NULL")


@pytest.mark.unit
def test_event_processing_rows_are_registered_in_storage_metadata() -> None:
    assert StorageBase.metadata.tables["pmrp_event.processed_events"] is ProcessedEventRow.__table__
    assert StorageBase.metadata.tables["pmrp_event.outbox_messages"] is OutboxMessageRow.__table__
