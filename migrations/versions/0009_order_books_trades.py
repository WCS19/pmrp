"""Create order-book projection and trade tables.

Revision ID: 0009_order_books_trades
Revises: 0008_market_catalog_tables
Create Date: 2026-07-29

Lock risk: low on empty databases; creates one projection table, one partitioned
trade table, and three indexes in pmrp_market.
Expected runtime: under one second on empty local and CI PostgreSQL databases.
Rollback plan: downgrade drops trades, then order_book_snapshots.
Backfill plan: not applicable; no rows are created or transformed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_order_books_trades"
down_revision: str | None = "0008_market_catalog_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_NAME = "pmrp_market"
ORDER_BOOK_SNAPSHOTS_TABLE_NAME = "order_book_snapshots"
TRADES_TABLE_NAME = "trades"
ORDER_BOOK_EXCHANGE_UPDATED_INDEX_NAME = "ix_order_book_snapshots__exchange_updated"
TRADES_MARKET_TIME_INDEX_NAME = "ix_trades__market_time"
TRADES_CONTRACT_TIME_INDEX_NAME = "ix_trades__contract_time"
ORDER_BOOK_MARKET_FOREIGN_KEY_NAME = "fk_order_book_snapshots__market_id__markets"
ORDER_BOOK_CONTRACT_FOREIGN_KEY_NAME = "fk_order_book_snapshots__contract_id__contracts"
TRADES_QUANTITY_CHECK_NAME = "ck_trades__quantity"


def upgrade() -> None:
    """Create current order-book projection and trade observation storage."""

    op.create_table(
        ORDER_BOOK_SNAPSHOTS_TABLE_NAME,
        sa.Column("market_id", sa.Text(), nullable=False),
        sa.Column("contract_id", sa.Text(), nullable=False),
        sa.Column("exchange", sa.Text(), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=True),
        sa.Column("exchange_occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bids", postgresql.JSONB(), nullable=False),
        sa.Column("asks", postgresql.JSONB(), nullable=False),
        sa.Column("is_valid", sa.Boolean(), nullable=False),
        sa.Column("snapshot_reason", sa.Text(), nullable=False),
        sa.Column(
            "aggregate_version",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("market_id", "contract_id", name="pk_order_book_snapshots"),
        sa.ForeignKeyConstraint(
            ["market_id"],
            [f"{SCHEMA_NAME}.markets.market_id"],
            name=op.f(ORDER_BOOK_MARKET_FOREIGN_KEY_NAME),
        ),
        sa.ForeignKeyConstraint(
            ["contract_id"],
            [f"{SCHEMA_NAME}.contracts.contract_id"],
            name=op.f(ORDER_BOOK_CONTRACT_FOREIGN_KEY_NAME),
        ),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        ORDER_BOOK_EXCHANGE_UPDATED_INDEX_NAME,
        ORDER_BOOK_SNAPSHOTS_TABLE_NAME,
        ["exchange", "updated_at"],
        schema=SCHEMA_NAME,
    )
    op.create_table(
        TRADES_TABLE_NAME,
        sa.Column("exchange_occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trade_id", sa.Text(), nullable=False),
        sa.Column("exchange", sa.Text(), nullable=False),
        sa.Column("exchange_trade_id", sa.Text(), nullable=False),
        sa.Column("market_id", sa.Text(), nullable=False),
        sa.Column("contract_id", sa.Text(), nullable=False),
        sa.Column("outcome_id", sa.Text(), nullable=False),
        sa.Column("price", sa.Numeric(38, 18), nullable=False),
        sa.Column("quantity", sa.Numeric(38, 18), nullable=False),
        sa.Column("aggressor_side", sa.Text(), nullable=True),
        sa.Column("liquidity_role", sa.Text(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=True),
        sa.Column("source_event_id", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("exchange_occurred_at", "trade_id", name="pk_trades"),
        sa.CheckConstraint("quantity > 0", name=op.f(TRADES_QUANTITY_CHECK_NAME)),
        schema=SCHEMA_NAME,
        postgresql_partition_by="RANGE (exchange_occurred_at)",
    )
    op.create_index(
        TRADES_MARKET_TIME_INDEX_NAME,
        TRADES_TABLE_NAME,
        ["market_id", sa.text("exchange_occurred_at DESC")],
        schema=SCHEMA_NAME,
    )
    op.create_index(
        TRADES_CONTRACT_TIME_INDEX_NAME,
        TRADES_TABLE_NAME,
        ["contract_id", sa.text("exchange_occurred_at DESC")],
        schema=SCHEMA_NAME,
    )


def downgrade() -> None:
    """Drop current order-book projection and trade observation storage."""

    op.drop_index(TRADES_CONTRACT_TIME_INDEX_NAME, table_name=TRADES_TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_index(TRADES_MARKET_TIME_INDEX_NAME, table_name=TRADES_TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_table(TRADES_TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_index(
        ORDER_BOOK_EXCHANGE_UPDATED_INDEX_NAME,
        table_name=ORDER_BOOK_SNAPSHOTS_TABLE_NAME,
        schema=SCHEMA_NAME,
    )
    op.drop_table(ORDER_BOOK_SNAPSHOTS_TABLE_NAME, schema=SCHEMA_NAME)
