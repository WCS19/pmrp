"""Create position, cash balance, and journal tables.

Revision ID: 0014_portfolio_storage
Revises: 0013_fills_registry
Create Date: 2026-07-29

Lock risk: low on empty databases; creates four unpartitioned tables and three
indexes in pmrp_portfolio.
Expected runtime: under one second on empty local and CI PostgreSQL databases.
Rollback plan: downgrade drops journal_lines, journal_entries, cash_balances,
then positions.
Backfill plan: not applicable; no rows are created or transformed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_portfolio_storage"
down_revision: str | None = "0013_fills_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_NAME = "pmrp_portfolio"
POSITIONS_TABLE_NAME = "positions"
CASH_BALANCES_TABLE_NAME = "cash_balances"
JOURNAL_ENTRIES_TABLE_NAME = "journal_entries"
JOURNAL_LINES_TABLE_NAME = "journal_lines"
POSITIONS_ACCOUNT_MARKET_INDEX_NAME = "ix_positions__account_market"
JOURNAL_ENTRIES_REFERENCE_INDEX_NAME = "ix_journal_entries__reference"
JOURNAL_LINES_ACCOUNT_CURRENCY_INDEX_NAME = "ix_journal_lines__account_currency"
POSITIONS_ACCOUNT_CONTRACT_UNIQUE_NAME = "uq_positions__exchange_account_contract"
CASH_BALANCES_ACCOUNT_CURRENCY_UNIQUE_NAME = "uq_cash_balances__exchange_account_currency"
CASH_BALANCES_IDENTITY_CHECK_NAME = "ck_cash_balances__balance_identity"
JOURNAL_ENTRIES_SOURCE_EVENT_UNIQUE_NAME = "uq_journal_entries__source_event_id"
JOURNAL_LINES_ENTRY_FOREIGN_KEY_NAME = "fk_journal_lines__journal_entry_id__journal_entries"


def upgrade() -> None:
    """Create current portfolio projections and append-only journal storage."""

    op.create_table(
        POSITIONS_TABLE_NAME,
        sa.Column("position_id", sa.Text(), nullable=False),
        sa.Column("exchange", sa.Text(), nullable=False),
        sa.Column("account_id", sa.Text(), nullable=False),
        sa.Column("market_id", sa.Text(), nullable=False),
        sa.Column("contract_id", sa.Text(), nullable=False),
        sa.Column("outcome_id", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Numeric(38, 18), nullable=False),
        sa.Column("average_entry_price", sa.Numeric(38, 18), nullable=True),
        sa.Column(
            "realized_pnl_amount",
            sa.Numeric(38, 18),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "unrealized_pnl_amount",
            sa.Numeric(38, 18),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column(
            "fees_paid_amount",
            sa.Numeric(38, 18),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "rebates_received_amount",
            sa.Numeric(38, 18),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "aggregate_version",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.PrimaryKeyConstraint("position_id", name="pk_positions"),
        sa.UniqueConstraint(
            "exchange",
            "account_id",
            "contract_id",
            name=op.f(POSITIONS_ACCOUNT_CONTRACT_UNIQUE_NAME),
        ),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        POSITIONS_ACCOUNT_MARKET_INDEX_NAME,
        POSITIONS_TABLE_NAME,
        ["exchange", "account_id", "market_id"],
        schema=SCHEMA_NAME,
    )
    op.create_table(
        CASH_BALANCES_TABLE_NAME,
        sa.Column("balance_id", sa.Text(), nullable=False),
        sa.Column("exchange", sa.Text(), nullable=False),
        sa.Column("account_id", sa.Text(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("available", sa.Numeric(38, 18), nullable=False),
        sa.Column("reserved", sa.Numeric(38, 18), nullable=False),
        sa.Column("total", sa.Numeric(38, 18), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "aggregate_version",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.PrimaryKeyConstraint("balance_id", name="pk_cash_balances"),
        sa.UniqueConstraint(
            "exchange",
            "account_id",
            "currency",
            name=op.f(CASH_BALANCES_ACCOUNT_CURRENCY_UNIQUE_NAME),
        ),
        sa.CheckConstraint(
            "available + reserved = total",
            name=op.f(CASH_BALANCES_IDENTITY_CHECK_NAME),
        ),
        schema=SCHEMA_NAME,
    )
    op.create_table(
        JOURNAL_ENTRIES_TABLE_NAME,
        sa.Column("journal_entry_id", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_event_id", sa.Text(), nullable=False),
        sa.Column("reference_type", sa.Text(), nullable=False),
        sa.Column("reference_id", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("journal_entry_id", name="pk_journal_entries"),
        sa.UniqueConstraint(
            "source_event_id",
            name=op.f(JOURNAL_ENTRIES_SOURCE_EVENT_UNIQUE_NAME),
        ),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        JOURNAL_ENTRIES_REFERENCE_INDEX_NAME,
        JOURNAL_ENTRIES_TABLE_NAME,
        ["reference_type", "reference_id"],
        schema=SCHEMA_NAME,
    )
    op.create_table(
        JOURNAL_LINES_TABLE_NAME,
        sa.Column("journal_entry_id", sa.Text(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("account_code", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(38, 18), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("journal_entry_id", "line_number", name="pk_journal_lines"),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"],
            [f"{SCHEMA_NAME}.{JOURNAL_ENTRIES_TABLE_NAME}.journal_entry_id"],
            name=op.f(JOURNAL_LINES_ENTRY_FOREIGN_KEY_NAME),
        ),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        JOURNAL_LINES_ACCOUNT_CURRENCY_INDEX_NAME,
        JOURNAL_LINES_TABLE_NAME,
        ["account_code", "currency"],
        schema=SCHEMA_NAME,
    )


def downgrade() -> None:
    """Drop current portfolio projections and append-only journal storage."""

    op.drop_index(
        JOURNAL_LINES_ACCOUNT_CURRENCY_INDEX_NAME,
        table_name=JOURNAL_LINES_TABLE_NAME,
        schema=SCHEMA_NAME,
    )
    op.drop_table(JOURNAL_LINES_TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_index(
        JOURNAL_ENTRIES_REFERENCE_INDEX_NAME,
        table_name=JOURNAL_ENTRIES_TABLE_NAME,
        schema=SCHEMA_NAME,
    )
    op.drop_table(JOURNAL_ENTRIES_TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_table(CASH_BALANCES_TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_index(
        POSITIONS_ACCOUNT_MARKET_INDEX_NAME,
        table_name=POSITIONS_TABLE_NAME,
        schema=SCHEMA_NAME,
    )
    op.drop_table(POSITIONS_TABLE_NAME, schema=SCHEMA_NAME)
