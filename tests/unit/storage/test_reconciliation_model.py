"""Tests for reconciliation SQLAlchemy row models."""

from __future__ import annotations

import pytest
from sqlalchemy import ForeignKeyConstraint
from sqlalchemy.dialects import postgresql

from pmrp.storage.models import (
    ReconciliationMismatchRow,
    ReconciliationRunRow,
    StorageBase,
)


@pytest.mark.unit
def test_reconciliation_run_row_mapping_matches_database_spec() -> None:
    table = ReconciliationRunRow.__table__

    assert table.schema == "pmrp_ops"
    assert table.name == "reconciliation_runs"
    assert [column.name for column in table.primary_key.columns] == ["reconciliation_id"]
    assert set(table.columns.keys()) == {
        "reconciliation_id",
        "exchange",
        "account_id",
        "started_at",
        "completed_at",
        "status",
        "open_orders_checked",
        "positions_checked",
        "balances_checked",
        "fills_checked",
        "trading_gate_released",
        "initiated_by",
        "reason",
        "created_at",
    }


@pytest.mark.unit
def test_reconciliation_run_defaults_and_indexes_match_database_spec() -> None:
    table = ReconciliationRunRow.__table__
    account_time_index = next(
        index for index in table.indexes if index.name == "ix_reconciliation_runs__account_time"
    )

    assert [expression.name for expression in account_time_index.expressions[:2]] == [
        "exchange",
        "account_id",
    ]
    assert str(account_time_index.expressions[2].compile(dialect=postgresql.dialect())) == (
        "started_at DESC"
    )
    assert str(table.columns["open_orders_checked"].server_default.arg) == "0"
    assert str(table.columns["positions_checked"].server_default.arg) == "0"
    assert str(table.columns["balances_checked"].server_default.arg) == "0"
    assert str(table.columns["fills_checked"].server_default.arg) == "0"
    assert str(table.columns["trading_gate_released"].server_default.arg) == "false"
    assert str(table.columns["created_at"].server_default.arg) == "now()"


@pytest.mark.unit
def test_reconciliation_mismatch_row_mapping_matches_database_spec() -> None:
    table = ReconciliationMismatchRow.__table__

    assert table.schema == "pmrp_ops"
    assert table.name == "reconciliation_mismatches"
    assert [column.name for column in table.primary_key.columns] == ["mismatch_id"]
    assert set(table.columns.keys()) == {
        "mismatch_id",
        "reconciliation_id",
        "category",
        "local_value",
        "external_value",
        "severity",
        "explanation",
        "requires_manual_review",
        "resolved_at",
        "resolution_note",
    }


@pytest.mark.unit
def test_reconciliation_mismatch_constraints_and_indexes_match_database_spec() -> None:
    table = ReconciliationMismatchRow.__table__
    run_index = next(
        index for index in table.indexes if index.name == "ix_reconciliation_mismatches__run"
    )
    foreign_key = next(
        constraint
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    )

    assert foreign_key.name == "fk_reconciliation_mismatches__reconciliation_runs"
    assert [column.name for column in foreign_key.columns] == ["reconciliation_id"]
    assert [element.target_fullname for element in foreign_key.elements] == [
        "pmrp_ops.reconciliation_runs.reconciliation_id"
    ]
    assert [column.name for column in run_index.columns] == [
        "reconciliation_id",
        "severity",
    ]


@pytest.mark.unit
def test_reconciliation_rows_are_registered_in_storage_metadata() -> None:
    assert (
        StorageBase.metadata.tables["pmrp_ops.reconciliation_runs"]
        is ReconciliationRunRow.__table__
    )
    assert (
        StorageBase.metadata.tables["pmrp_ops.reconciliation_mismatches"]
        is ReconciliationMismatchRow.__table__
    )
