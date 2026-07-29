"""Tests for research signal and feature snapshot SQLAlchemy row models."""

from __future__ import annotations

import pytest
from sqlalchemy import Numeric, Table

from pmrp.storage.models import FeatureSnapshotRow, SignalRow, StorageBase


@pytest.mark.unit
def test_signal_row_mapping_matches_database_spec() -> None:
    table = SignalRow.__table__

    assert table.schema == "pmrp_research"
    assert table.name == "signals"
    assert [column.name for column in table.primary_key.columns] == [
        "generated_at",
        "signal_id",
    ]
    assert set(table.columns.keys()) == {
        "generated_at",
        "signal_id",
        "strategy_id",
        "market_id",
        "contract_id",
        "outcome_id",
        "signal_type",
        "direction",
        "strength",
        "fair_probability",
        "confidence",
        "valid_from",
        "valid_until",
        "model_id",
        "model_version",
        "feature_snapshot_id",
        "reason_code",
        "reason_text",
        "correlation_id",
        "source_event_id",
    }


@pytest.mark.unit
def test_signal_partitioning_matches_database_spec() -> None:
    assert SignalRow.__table__.dialect_options["postgresql"]["partition_by"] == (
        "RANGE (generated_at)"
    )


@pytest.mark.unit
def test_signal_constraints_and_indexes_match_database_spec() -> None:
    table = SignalRow.__table__

    assert {"ck_signals__fair_probability"} <= {constraint.name for constraint in table.constraints}
    assert {"ix_signals__market_time", "ix_signals__strategy_time"} <= {
        index.name for index in table.indexes
    }


@pytest.mark.unit
def test_feature_snapshot_row_mapping_matches_database_spec() -> None:
    table = FeatureSnapshotRow.__table__

    assert table.schema == "pmrp_research"
    assert table.name == "feature_snapshots"
    assert [column.name for column in table.primary_key.columns] == [
        "observed_at",
        "feature_snapshot_id",
    ]
    assert set(table.columns.keys()) == {
        "observed_at",
        "feature_snapshot_id",
        "market_id",
        "strategy_id",
        "generated_at",
        "schema_version",
        "calculation_version",
        "features",
        "source_event_ids",
        "payload_hash",
    }


@pytest.mark.unit
def test_feature_snapshot_partitioning_matches_database_spec() -> None:
    assert FeatureSnapshotRow.__table__.dialect_options["postgresql"]["partition_by"] == (
        "RANGE (observed_at)"
    )


@pytest.mark.unit
def test_feature_snapshot_indexes_match_database_spec() -> None:
    assert {"ix_feature_snapshots__market_time"} <= {
        index.name for index in FeatureSnapshotRow.__table__.indexes
    }


@pytest.mark.unit
@pytest.mark.parametrize(
    ("table", "column_name"),
    [
        (SignalRow.__table__, "strength"),
        (SignalRow.__table__, "fair_probability"),
        (SignalRow.__table__, "confidence"),
    ],
)
def test_signal_numeric_columns_use_exact_database_scale(
    table: Table,
    column_name: str,
) -> None:
    column = table.columns[column_name]

    assert isinstance(column.type, Numeric)
    assert column.type.precision == 38
    assert column.type.scale == 18


@pytest.mark.unit
def test_research_signal_rows_are_registered_in_storage_metadata() -> None:
    assert StorageBase.metadata.tables["pmrp_research.signals"] is SignalRow.__table__
    assert (
        StorageBase.metadata.tables["pmrp_research.feature_snapshots"]
        is FeatureSnapshotRow.__table__
    )
