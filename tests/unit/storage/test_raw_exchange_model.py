"""Tests for the raw exchange record SQLAlchemy row model."""

from __future__ import annotations

import pytest

from pmrp.storage.models import RawExchangeRecordRow, StorageBase


@pytest.mark.unit
def test_raw_exchange_record_row_mapping_matches_database_spec() -> None:
    table = RawExchangeRecordRow.__table__

    assert table.schema == "pmrp_raw"
    assert table.name == "exchange_records"
    assert [column.name for column in table.primary_key.columns] == [
        "received_at",
        "raw_record_id",
    ]
    assert set(table.columns.keys()) == {
        "received_at",
        "raw_record_id",
        "exchange",
        "environment",
        "connection_id",
        "endpoint",
        "channel",
        "message_type",
        "exchange_occurred_at",
        "sequence",
        "content_type",
        "compression",
        "payload_text",
        "payload_bytes",
        "payload_hash",
        "parser_version",
        "transport_metadata",
        "inserted_at",
    }


@pytest.mark.unit
def test_raw_exchange_record_row_partitioning_matches_database_spec() -> None:
    assert (
        RawExchangeRecordRow.__table__.dialect_options["postgresql"]["partition_by"]
        == "RANGE (received_at)"
    )


@pytest.mark.unit
def test_raw_exchange_record_constraints_and_indexes_match_database_spec() -> None:
    table = RawExchangeRecordRow.__table__

    assert "ck_exchange_records__payload_storage" in {
        constraint.name for constraint in table.constraints
    }
    assert {
        "ix_exchange_records__exchange_received",
        "ix_exchange_records__channel_received",
        "ix_exchange_records__payload_hash",
    } <= {index.name for index in table.indexes}


@pytest.mark.unit
def test_raw_exchange_record_row_is_registered_in_storage_metadata() -> None:
    assert (
        StorageBase.metadata.tables["pmrp_raw.exchange_records"] is RawExchangeRecordRow.__table__
    )
