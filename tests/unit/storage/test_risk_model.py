"""Tests for risk SQLAlchemy row models."""

from __future__ import annotations

import pytest
from sqlalchemy import Numeric, Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB

from pmrp.storage.models import RiskBreachRow, RiskDecisionRow, RiskLimitRow, StorageBase


@pytest.mark.unit
def test_risk_limit_row_mapping_matches_database_spec() -> None:
    table = RiskLimitRow.__table__

    assert table.schema == "pmrp_risk"
    assert table.name == "risk_limits"
    assert [column.name for column in table.primary_key.columns] == ["risk_limit_id"]
    assert set(table.columns.keys()) == {
        "risk_limit_id",
        "rule_id",
        "rule_version",
        "scope",
        "scope_id",
        "limit_type",
        "limit_value",
        "unit",
        "effective_at",
        "expires_at",
        "enabled",
        "created_by",
        "approved_by",
        "created_at",
        "updated_at",
        "aggregate_version",
    }


@pytest.mark.unit
def test_risk_limit_active_scope_index_matches_database_spec() -> None:
    active_index = next(
        index
        for index in RiskLimitRow.__table__.indexes
        if index.name == "ix_risk_limits__active_scope"
    )

    assert [column.name for column in active_index.columns] == [
        "scope",
        "scope_id",
        "rule_id",
    ]
    assert str(active_index.dialect_options["postgresql"]["where"]) == "enabled = true"


@pytest.mark.unit
def test_risk_decision_row_mapping_matches_database_spec() -> None:
    table = RiskDecisionRow.__table__

    assert table.schema == "pmrp_risk"
    assert table.name == "risk_decisions"
    assert [column.name for column in table.primary_key.columns] == [
        "evaluated_at",
        "risk_decision_id",
    ]
    assert set(table.columns.keys()) == {
        "evaluated_at",
        "risk_decision_id",
        "intent_id",
        "status",
        "input_snapshot_id",
        "approved_quantity",
        "approved_limit_price",
        "approval_expires_at",
        "configuration_hash",
        "correlation_id",
        "rule_results",
        "payload_hash",
    }


@pytest.mark.unit
def test_risk_decision_partitioning_and_indexes_match_database_spec() -> None:
    table = RiskDecisionRow.__table__
    status_index = next(
        index for index in table.indexes if index.name == "ix_risk_decisions__status_time"
    )

    assert table.dialect_options["postgresql"]["partition_by"] == "RANGE (evaluated_at)"
    assert {"ix_risk_decisions__intent", "ix_risk_decisions__status_time"} <= {
        index.name for index in table.indexes
    }
    assert str(status_index.expressions[1].compile(dialect=postgresql.dialect())) == (
        "evaluated_at DESC"
    )


@pytest.mark.unit
def test_risk_decision_rule_results_use_jsonb() -> None:
    assert isinstance(RiskDecisionRow.__table__.columns["rule_results"].type, JSONB)


@pytest.mark.unit
def test_risk_breach_row_mapping_matches_database_spec() -> None:
    table = RiskBreachRow.__table__

    assert table.schema == "pmrp_risk"
    assert table.name == "risk_breaches"
    assert [column.name for column in table.primary_key.columns] == ["breach_id"]
    assert set(table.columns.keys()) == {
        "breach_id",
        "rule_id",
        "rule_version",
        "scope",
        "scope_id",
        "severity",
        "detected_at",
        "observed_value",
        "limit_value",
        "unit",
        "action_taken",
        "correlation_id",
        "resolved_at",
        "resolution_note",
    }


@pytest.mark.unit
def test_risk_breach_open_severity_index_matches_database_spec() -> None:
    open_index = next(
        index
        for index in RiskBreachRow.__table__.indexes
        if index.name == "ix_risk_breaches__open_severity"
    )

    assert str(open_index.expressions[1].compile(dialect=postgresql.dialect())) == (
        "detected_at DESC"
    )
    assert str(open_index.dialect_options["postgresql"]["where"]) == "resolved_at IS NULL"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("table", "column_name"),
    [
        (RiskLimitRow.__table__, "limit_value"),
        (RiskDecisionRow.__table__, "approved_quantity"),
        (RiskDecisionRow.__table__, "approved_limit_price"),
        (RiskBreachRow.__table__, "observed_value"),
        (RiskBreachRow.__table__, "limit_value"),
    ],
)
def test_risk_numeric_columns_use_exact_database_scale(
    table: Table,
    column_name: str,
) -> None:
    column = table.columns[column_name]

    assert isinstance(column.type, Numeric)
    assert column.type.precision == 38
    assert column.type.scale == 18


@pytest.mark.unit
def test_risk_rows_are_registered_in_storage_metadata() -> None:
    assert StorageBase.metadata.tables["pmrp_risk.risk_limits"] is RiskLimitRow.__table__
    assert StorageBase.metadata.tables["pmrp_risk.risk_decisions"] is RiskDecisionRow.__table__
    assert StorageBase.metadata.tables["pmrp_risk.risk_breaches"] is RiskBreachRow.__table__
