"""Tests for canonical event SQLAlchemy row models."""

from __future__ import annotations

import pytest

from pmrp.storage.models import CanonicalEventRow, EventIdRow, StorageBase


@pytest.mark.unit
def test_event_id_row_mapping_matches_database_spec() -> None:
    table = EventIdRow.__table__

    assert table.schema == "pmrp_event"
    assert table.name == "event_ids"
    assert [column.name for column in table.primary_key.columns] == ["event_id"]
    assert set(table.columns.keys()) == {
        "event_id",
        "occurred_at",
        "inserted_at",
    }


@pytest.mark.unit
def test_canonical_event_row_mapping_matches_database_spec() -> None:
    table = CanonicalEventRow.__table__

    assert table.schema == "pmrp_event"
    assert table.name == "canonical_events"
    assert [column.name for column in table.primary_key.columns] == [
        "occurred_at",
        "event_id",
    ]
    assert set(table.columns.keys()) == {
        "occurred_at",
        "event_id",
        "event_type",
        "schema_version",
        "received_at",
        "published_at",
        "producer",
        "exchange",
        "market_id",
        "account_id",
        "strategy_id",
        "order_id",
        "correlation_id",
        "causation_id",
        "trace_id",
        "replay_session_id",
        "simulation_session_id",
        "quality_flags",
        "attributes",
        "payload",
        "payload_hash",
        "inserted_at",
    }


@pytest.mark.unit
def test_canonical_event_partitioning_matches_database_spec() -> None:
    assert (
        CanonicalEventRow.__table__.dialect_options["postgresql"]["partition_by"]
        == "RANGE (occurred_at)"
    )


@pytest.mark.unit
def test_canonical_event_constraints_and_indexes_match_database_spec() -> None:
    table = CanonicalEventRow.__table__

    assert "ck_canonical_events__schema_version" in {
        constraint.name for constraint in table.constraints
    }
    assert {
        "ix_canonical_events__type_time",
        "ix_canonical_events__market_time",
        "ix_canonical_events__order_time",
        "ix_canonical_events__correlation",
    } <= {index.name for index in table.indexes}


@pytest.mark.unit
def test_canonical_event_rows_are_registered_in_storage_metadata() -> None:
    assert StorageBase.metadata.tables["pmrp_event.event_ids"] is EventIdRow.__table__
    assert StorageBase.metadata.tables["pmrp_event.canonical_events"] is CanonicalEventRow.__table__
