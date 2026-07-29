"""Tests for portfolio SQLAlchemy row models."""

from __future__ import annotations

import pytest
from sqlalchemy import Numeric, Table

from pmrp.storage.models import (
    CashBalanceRow,
    JournalEntryRow,
    JournalLineRow,
    PnlAttributionRow,
    PositionRow,
    SettlementRow,
    StorageBase,
)


@pytest.mark.unit
def test_position_row_mapping_matches_database_spec() -> None:
    table = PositionRow.__table__

    assert table.schema == "pmrp_portfolio"
    assert table.name == "positions"
    assert [column.name for column in table.primary_key.columns] == ["position_id"]
    assert set(table.columns.keys()) == {
        "position_id",
        "exchange",
        "account_id",
        "market_id",
        "contract_id",
        "outcome_id",
        "quantity",
        "average_entry_price",
        "realized_pnl_amount",
        "unrealized_pnl_amount",
        "currency",
        "fees_paid_amount",
        "rebates_received_amount",
        "opened_at",
        "last_updated_at",
        "aggregate_version",
    }


@pytest.mark.unit
def test_position_constraints_and_indexes_match_database_spec() -> None:
    table = PositionRow.__table__

    assert {"uq_positions__exchange_account_contract"} <= {
        constraint.name for constraint in table.constraints
    }
    assert {"ix_positions__account_market"} <= {index.name for index in table.indexes}


@pytest.mark.unit
def test_cash_balance_row_mapping_matches_database_spec() -> None:
    table = CashBalanceRow.__table__

    assert table.schema == "pmrp_portfolio"
    assert table.name == "cash_balances"
    assert [column.name for column in table.primary_key.columns] == ["balance_id"]
    assert set(table.columns.keys()) == {
        "balance_id",
        "exchange",
        "account_id",
        "currency",
        "available",
        "reserved",
        "total",
        "captured_at",
        "aggregate_version",
    }


@pytest.mark.unit
def test_cash_balance_constraints_match_database_spec() -> None:
    table = CashBalanceRow.__table__

    assert {
        "ck_cash_balances__balance_identity",
        "uq_cash_balances__exchange_account_currency",
    } <= {constraint.name for constraint in table.constraints}


@pytest.mark.unit
def test_journal_entry_row_mapping_matches_database_spec() -> None:
    table = JournalEntryRow.__table__

    assert table.schema == "pmrp_portfolio"
    assert table.name == "journal_entries"
    assert [column.name for column in table.primary_key.columns] == ["journal_entry_id"]
    assert set(table.columns.keys()) == {
        "journal_entry_id",
        "occurred_at",
        "source_event_id",
        "reference_type",
        "reference_id",
        "description",
        "created_at",
    }


@pytest.mark.unit
def test_journal_entry_constraints_and_indexes_match_database_spec() -> None:
    table = JournalEntryRow.__table__

    assert {"uq_journal_entries__source_event_id"} <= {
        constraint.name for constraint in table.constraints
    }
    assert {"ix_journal_entries__reference"} <= {index.name for index in table.indexes}


@pytest.mark.unit
def test_journal_line_row_mapping_matches_database_spec() -> None:
    table = JournalLineRow.__table__

    assert table.schema == "pmrp_portfolio"
    assert table.name == "journal_lines"
    assert [column.name for column in table.primary_key.columns] == [
        "journal_entry_id",
        "line_number",
    ]
    assert set(table.columns.keys()) == {
        "journal_entry_id",
        "line_number",
        "account_code",
        "amount",
        "currency",
        "description",
    }


@pytest.mark.unit
def test_journal_line_constraints_and_indexes_match_database_spec() -> None:
    table = JournalLineRow.__table__

    assert {"fk_journal_lines__journal_entry_id__journal_entries"} <= {
        constraint.name for constraint in table.constraints
    }
    assert {"ix_journal_lines__account_currency"} <= {index.name for index in table.indexes}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("table", "column_name"),
    [
        (PositionRow.__table__, "quantity"),
        (PositionRow.__table__, "average_entry_price"),
        (PositionRow.__table__, "realized_pnl_amount"),
        (PositionRow.__table__, "unrealized_pnl_amount"),
        (PositionRow.__table__, "fees_paid_amount"),
        (PositionRow.__table__, "rebates_received_amount"),
        (CashBalanceRow.__table__, "available"),
        (CashBalanceRow.__table__, "reserved"),
        (CashBalanceRow.__table__, "total"),
        (JournalLineRow.__table__, "amount"),
    ],
)
def test_portfolio_numeric_columns_use_exact_database_scale(
    table: Table,
    column_name: str,
) -> None:
    column = table.columns[column_name]

    assert isinstance(column.type, Numeric)
    assert column.type.precision == 38
    assert column.type.scale == 18


@pytest.mark.unit
def test_pnl_attribution_row_mapping_matches_database_spec() -> None:
    table = PnlAttributionRow.__table__

    assert table.schema == "pmrp_portfolio"
    assert table.name == "pnl_attributions"
    assert [column.name for column in table.primary_key.columns] == ["attribution_id"]
    assert set(table.columns.keys()) == {
        "attribution_id",
        "strategy_id",
        "market_id",
        "exchange",
        "starts_at",
        "ends_at",
        "currency",
        "realized_trading_pnl",
        "unrealized_pnl_change",
        "fees",
        "rebates",
        "slippage",
        "settlement_pnl",
        "total_pnl",
        "calculation_version",
        "created_at",
    }


@pytest.mark.unit
def test_pnl_attribution_indexes_match_database_spec() -> None:
    assert {"ix_pnl_attributions__strategy_period"} <= {
        index.name for index in PnlAttributionRow.__table__.indexes
    }


@pytest.mark.unit
def test_settlement_row_mapping_matches_database_spec() -> None:
    table = SettlementRow.__table__

    assert table.schema == "pmrp_portfolio"
    assert table.name == "settlements"
    assert [column.name for column in table.primary_key.columns] == ["settlement_id"]
    assert set(table.columns.keys()) == {
        "settlement_id",
        "market_id",
        "exchange",
        "status",
        "winning_outcome_ids",
        "resolved_at",
        "finalized_at",
        "settled_at",
        "payout_per_unit",
        "source",
        "source_reference",
        "correction_of_settlement_id",
        "created_at",
    }


@pytest.mark.unit
def test_settlement_constraints_and_indexes_match_database_spec() -> None:
    table = SettlementRow.__table__

    assert {"fk_settlements__correction_of_settlement_id__settlements"} <= {
        constraint.name for constraint in table.constraints
    }
    assert {"ix_settlements__market_created"} <= {index.name for index in table.indexes}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("table", "column_name"),
    [
        (PnlAttributionRow.__table__, "realized_trading_pnl"),
        (PnlAttributionRow.__table__, "unrealized_pnl_change"),
        (PnlAttributionRow.__table__, "fees"),
        (PnlAttributionRow.__table__, "rebates"),
        (PnlAttributionRow.__table__, "slippage"),
        (PnlAttributionRow.__table__, "settlement_pnl"),
        (PnlAttributionRow.__table__, "total_pnl"),
        (SettlementRow.__table__, "payout_per_unit"),
    ],
)
def test_pnl_settlement_numeric_columns_use_exact_database_scale(
    table: Table,
    column_name: str,
) -> None:
    column = table.columns[column_name]

    assert isinstance(column.type, Numeric)
    assert column.type.precision == 38
    assert column.type.scale == 18


@pytest.mark.unit
def test_portfolio_rows_are_registered_in_storage_metadata() -> None:
    assert StorageBase.metadata.tables["pmrp_portfolio.positions"] is PositionRow.__table__
    assert StorageBase.metadata.tables["pmrp_portfolio.cash_balances"] is CashBalanceRow.__table__
    assert (
        StorageBase.metadata.tables["pmrp_portfolio.journal_entries"] is JournalEntryRow.__table__
    )
    assert StorageBase.metadata.tables["pmrp_portfolio.journal_lines"] is JournalLineRow.__table__
    assert (
        StorageBase.metadata.tables["pmrp_portfolio.pnl_attributions"]
        is PnlAttributionRow.__table__
    )
    assert StorageBase.metadata.tables["pmrp_portfolio.settlements"] is SettlementRow.__table__
