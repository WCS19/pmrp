"""Tests for risk SQLAlchemy row models."""

from __future__ import annotations

import pytest
from sqlalchemy import CheckConstraint, Numeric, Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB

from pmrp.storage.models import (
    CapitalReservationRow,
    KillSwitchRow,
    RiskBreachRow,
    RiskDecisionRow,
    RiskInputSnapshotRow,
    RiskLimitRow,
    StorageBase,
)


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
def test_risk_input_snapshot_row_mapping_matches_database_spec() -> None:
    table = RiskInputSnapshotRow.__table__

    assert table.schema == "pmrp_risk"
    assert table.name == "risk_input_snapshots"
    assert [column.name for column in table.primary_key.columns] == ["risk_input_snapshot_id"]
    assert set(table.columns.keys()) == {
        "risk_input_snapshot_id",
        "captured_at",
        "strategy_id",
        "exchange",
        "account_id",
        "market_id",
        "current_position",
        "open_order_quantity",
        "available_balance",
        "gross_exposure",
        "net_exposure",
        "daily_realized_pnl",
        "daily_unrealized_pnl",
        "market_data_age_ms",
        "reconciliation_healthy",
        "kill_switch_clear",
        "payload_hash",
    }


@pytest.mark.unit
def test_risk_input_snapshot_indexes_match_database_spec() -> None:
    table = RiskInputSnapshotRow.__table__
    strategy_time_index = next(
        index for index in table.indexes if index.name == "ix_risk_input_snapshots__strategy_time"
    )
    account_market_time_index = next(
        index
        for index in table.indexes
        if index.name == "ix_risk_input_snapshots__account_market_time"
    )

    assert {
        "ix_risk_input_snapshots__strategy_time",
        "ix_risk_input_snapshots__account_market_time",
        "ix_risk_input_snapshots__payload_hash",
    } <= {index.name for index in table.indexes}
    assert [
        str(expression.compile(dialect=postgresql.dialect()))
        for expression in strategy_time_index.expressions
    ] == ["pmrp_risk.risk_input_snapshots.strategy_id", "captured_at DESC"]
    assert [
        str(expression.compile(dialect=postgresql.dialect()))
        for expression in account_market_time_index.expressions
    ] == [
        "pmrp_risk.risk_input_snapshots.exchange",
        "pmrp_risk.risk_input_snapshots.account_id",
        "pmrp_risk.risk_input_snapshots.market_id",
        "captured_at DESC",
    ]


@pytest.mark.unit
def test_risk_input_snapshot_check_constraints_match_schema_invariants() -> None:
    check_constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in RiskInputSnapshotRow.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert check_constraints == {
        "ck_risk_input_snapshots__open_order_quantity": "open_order_quantity >= 0",
        "ck_risk_input_snapshots__available_balance": "available_balance >= 0",
        "ck_risk_input_snapshots__gross_exposure": "gross_exposure >= 0",
        "ck_risk_input_snapshots__market_data_age": "market_data_age_ms >= 0",
    }


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
        (RiskInputSnapshotRow.__table__, "current_position"),
        (RiskInputSnapshotRow.__table__, "open_order_quantity"),
        (RiskInputSnapshotRow.__table__, "available_balance"),
        (RiskInputSnapshotRow.__table__, "gross_exposure"),
        (RiskInputSnapshotRow.__table__, "net_exposure"),
        (RiskInputSnapshotRow.__table__, "daily_realized_pnl"),
        (RiskInputSnapshotRow.__table__, "daily_unrealized_pnl"),
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
    assert (
        StorageBase.metadata.tables["pmrp_risk.risk_input_snapshots"]
        is RiskInputSnapshotRow.__table__
    )
    assert StorageBase.metadata.tables["pmrp_risk.risk_breaches"] is RiskBreachRow.__table__


@pytest.mark.unit
def test_kill_switch_row_mapping_matches_database_spec() -> None:
    table = KillSwitchRow.__table__

    assert table.schema == "pmrp_risk"
    assert table.name == "kill_switches"
    assert [column.name for column in table.primary_key.columns] == ["kill_switch_id"]
    assert set(table.columns.keys()) == {
        "kill_switch_id",
        "scope",
        "scope_id",
        "active",
        "activated_at",
        "activated_by",
        "activation_reason",
        "released_at",
        "released_by",
        "release_reason",
        "aggregate_version",
        "created_at",
        "updated_at",
    }


@pytest.mark.unit
def test_kill_switch_active_scope_index_matches_database_spec() -> None:
    active_index = next(
        index
        for index in KillSwitchRow.__table__.indexes
        if index.name == "uq_kill_switches__active_scope"
    )

    assert active_index.unique is True
    assert str(active_index.expressions[1]) == "COALESCE(scope_id, '')"
    assert str(active_index.dialect_options["postgresql"]["where"]) == "active = true"


@pytest.mark.unit
def test_capital_reservation_row_mapping_matches_database_spec() -> None:
    table = CapitalReservationRow.__table__

    assert table.schema == "pmrp_risk"
    assert table.name == "capital_reservations"
    assert [column.name for column in table.primary_key.columns] == ["reservation_id"]
    assert set(table.columns.keys()) == {
        "reservation_id",
        "intent_id",
        "strategy_id",
        "exchange",
        "account_id",
        "market_id",
        "quantity",
        "notional",
        "currency",
        "status",
        "created_at",
        "expires_at",
        "released_at",
    }


@pytest.mark.unit
def test_capital_reservation_constraints_and_indexes_match_database_spec() -> None:
    table = CapitalReservationRow.__table__
    active_expiry_index = next(
        index for index in table.indexes if index.name == "ix_capital_reservations__active_expiry"
    )

    assert {"uq_capital_reservations__intent_id"} <= {
        constraint.name for constraint in table.constraints
    }
    assert [column.name for column in active_expiry_index.columns] == ["expires_at"]
    assert str(active_expiry_index.dialect_options["postgresql"]["where"]) == (
        "released_at IS NULL"
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("table", "column_name"),
    [
        (CapitalReservationRow.__table__, "quantity"),
        (CapitalReservationRow.__table__, "notional"),
    ],
)
def test_reservation_numeric_columns_use_exact_database_scale(
    table: Table,
    column_name: str,
) -> None:
    column = table.columns[column_name]

    assert isinstance(column.type, Numeric)
    assert column.type.precision == 38
    assert column.type.scale == 18


@pytest.mark.unit
def test_kill_switch_and_reservation_rows_are_registered_in_storage_metadata() -> None:
    assert StorageBase.metadata.tables["pmrp_risk.kill_switches"] is KillSwitchRow.__table__
    assert (
        StorageBase.metadata.tables["pmrp_risk.capital_reservations"]
        is CapitalReservationRow.__table__
    )
