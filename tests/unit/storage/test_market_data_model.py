"""Tests for canonical market data SQLAlchemy row models."""

from __future__ import annotations

import pytest
from sqlalchemy import Numeric, Table

from pmrp.storage.models import OrderBookSnapshotRow, StorageBase, TradeRow


@pytest.mark.unit
def test_order_book_snapshot_row_mapping_matches_database_spec() -> None:
    table = OrderBookSnapshotRow.__table__

    assert table.schema == "pmrp_market"
    assert table.name == "order_book_snapshots"
    assert [column.name for column in table.primary_key.columns] == [
        "market_id",
        "contract_id",
    ]
    assert set(table.columns.keys()) == {
        "market_id",
        "contract_id",
        "exchange",
        "sequence",
        "exchange_occurred_at",
        "received_at",
        "bids",
        "asks",
        "is_valid",
        "snapshot_reason",
        "aggregate_version",
        "updated_at",
    }


@pytest.mark.unit
def test_order_book_snapshot_constraints_and_indexes_match_database_spec() -> None:
    table = OrderBookSnapshotRow.__table__

    assert {
        "fk_order_book_snapshots__contract_id__contracts",
        "fk_order_book_snapshots__market_id__markets",
    } <= {constraint.name for constraint in table.constraints}
    assert {"ix_order_book_snapshots__exchange_updated"} <= {index.name for index in table.indexes}


@pytest.mark.unit
def test_trade_row_mapping_matches_database_spec() -> None:
    table = TradeRow.__table__

    assert table.schema == "pmrp_market"
    assert table.name == "trades"
    assert [column.name for column in table.primary_key.columns] == [
        "exchange_occurred_at",
        "trade_id",
    ]
    assert set(table.columns.keys()) == {
        "exchange_occurred_at",
        "trade_id",
        "exchange",
        "exchange_trade_id",
        "market_id",
        "contract_id",
        "outcome_id",
        "price",
        "quantity",
        "aggressor_side",
        "liquidity_role",
        "received_at",
        "sequence",
        "source_event_id",
    }


@pytest.mark.unit
def test_trade_partitioning_matches_database_spec() -> None:
    assert (
        TradeRow.__table__.dialect_options["postgresql"]["partition_by"]
        == "RANGE (exchange_occurred_at)"
    )


@pytest.mark.unit
def test_trade_constraints_and_indexes_match_database_spec() -> None:
    table = TradeRow.__table__

    assert {"ck_trades__quantity"} <= {constraint.name for constraint in table.constraints}
    assert {"ix_trades__contract_time", "ix_trades__market_time"} <= {
        index.name for index in table.indexes
    }


@pytest.mark.unit
@pytest.mark.parametrize(
    ("table", "column_name"),
    [
        (TradeRow.__table__, "price"),
        (TradeRow.__table__, "quantity"),
    ],
)
def test_trade_numeric_columns_use_exact_database_scale(table: Table, column_name: str) -> None:
    column = table.columns[column_name]

    assert isinstance(column.type, Numeric)
    assert column.type.precision == 38
    assert column.type.scale == 18


@pytest.mark.unit
def test_market_data_rows_are_registered_in_storage_metadata() -> None:
    assert (
        StorageBase.metadata.tables["pmrp_market.order_book_snapshots"]
        is OrderBookSnapshotRow.__table__
    )
    assert StorageBase.metadata.tables["pmrp_market.trades"] is TradeRow.__table__
