"""Tests for canonical fill SQLAlchemy row models."""

from __future__ import annotations

import pytest
from sqlalchemy import Numeric, Table

from pmrp.storage.models import FillIdRow, FillRow, StorageBase


@pytest.mark.unit
def test_fill_row_mapping_matches_database_spec() -> None:
    table = FillRow.__table__

    assert table.schema == "pmrp_execution"
    assert table.name == "fills"
    assert [column.name for column in table.primary_key.columns] == [
        "exchange_occurred_at",
        "fill_id",
    ]
    assert set(table.columns.keys()) == {
        "exchange_occurred_at",
        "fill_id",
        "exchange_fill_id",
        "order_id",
        "exchange_order_id",
        "client_order_id",
        "exchange",
        "account_id",
        "market_id",
        "contract_id",
        "outcome_id",
        "side",
        "price",
        "quantity",
        "liquidity_role",
        "fee_amount",
        "fee_currency",
        "rebate_amount",
        "rebate_currency",
        "received_at",
        "trade_id",
        "source_event_id",
    }


@pytest.mark.unit
def test_fill_partitioning_matches_database_spec() -> None:
    assert FillRow.__table__.dialect_options["postgresql"]["partition_by"] == (
        "RANGE (exchange_occurred_at)"
    )


@pytest.mark.unit
def test_fill_constraints_and_indexes_match_database_spec() -> None:
    table = FillRow.__table__

    assert {"ck_fills__quantity"} <= {constraint.name for constraint in table.constraints}
    assert {"ix_fills__account_time", "ix_fills__order_time"} <= {
        index.name for index in table.indexes
    }


@pytest.mark.unit
def test_fill_id_row_mapping_matches_database_spec() -> None:
    table = FillIdRow.__table__

    assert table.schema == "pmrp_execution"
    assert table.name == "fill_ids"
    assert [column.name for column in table.primary_key.columns] == [
        "exchange",
        "account_id",
        "exchange_fill_id",
    ]
    assert set(table.columns.keys()) == {
        "exchange",
        "account_id",
        "exchange_fill_id",
        "fill_id",
        "exchange_occurred_at",
        "created_at",
    }


@pytest.mark.unit
def test_fill_id_constraints_match_database_spec() -> None:
    assert {"uq_fill_ids__fill_id"} <= {
        constraint.name for constraint in FillIdRow.__table__.constraints
    }


@pytest.mark.unit
@pytest.mark.parametrize(
    ("table", "column_name"),
    [
        (FillRow.__table__, "price"),
        (FillRow.__table__, "quantity"),
        (FillRow.__table__, "fee_amount"),
        (FillRow.__table__, "rebate_amount"),
    ],
)
def test_fill_numeric_columns_use_exact_database_scale(table: Table, column_name: str) -> None:
    column = table.columns[column_name]

    assert isinstance(column.type, Numeric)
    assert column.type.precision == 38
    assert column.type.scale == 18


@pytest.mark.unit
def test_fill_rows_are_registered_in_storage_metadata() -> None:
    assert StorageBase.metadata.tables["pmrp_execution.fills"] is FillRow.__table__
    assert StorageBase.metadata.tables["pmrp_execution.fill_ids"] is FillIdRow.__table__
