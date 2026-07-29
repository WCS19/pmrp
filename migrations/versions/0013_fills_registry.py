"""Create fill observation and fill ID registry tables.

Revision ID: 0013_fills_registry
Revises: 0012_order_storage
Create Date: 2026-07-29

Lock risk: low on empty databases; creates one partitioned table, one
unpartitioned registry table, and two indexes in pmrp_execution.
Expected runtime: under one second on empty local and CI PostgreSQL databases.
Rollback plan: downgrade drops fill_ids, then fills.
Backfill plan: not applicable; no rows are created or transformed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_fills_registry"
down_revision: str | None = "0012_order_storage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_NAME = "pmrp_execution"
FILLS_TABLE_NAME = "fills"
FILL_IDS_TABLE_NAME = "fill_ids"
FILLS_ORDER_TIME_INDEX_NAME = "ix_fills__order_time"
FILLS_ACCOUNT_TIME_INDEX_NAME = "ix_fills__account_time"
FILLS_QUANTITY_CHECK_NAME = "ck_fills__quantity"
FILL_IDS_FILL_ID_UNIQUE_NAME = "uq_fill_ids__fill_id"


def upgrade() -> None:
    """Create append-only fill storage and fill idempotency registry."""

    op.create_table(
        FILLS_TABLE_NAME,
        sa.Column("exchange_occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fill_id", sa.Text(), nullable=False),
        sa.Column("exchange_fill_id", sa.Text(), nullable=False),
        sa.Column("order_id", sa.Text(), nullable=False),
        sa.Column("exchange_order_id", sa.Text(), nullable=True),
        sa.Column("client_order_id", sa.Text(), nullable=False),
        sa.Column("exchange", sa.Text(), nullable=False),
        sa.Column("account_id", sa.Text(), nullable=False),
        sa.Column("market_id", sa.Text(), nullable=False),
        sa.Column("contract_id", sa.Text(), nullable=False),
        sa.Column("outcome_id", sa.Text(), nullable=False),
        sa.Column("side", sa.Text(), nullable=False),
        sa.Column("price", sa.Numeric(38, 18), nullable=False),
        sa.Column("quantity", sa.Numeric(38, 18), nullable=False),
        sa.Column("liquidity_role", sa.Text(), nullable=False),
        sa.Column("fee_amount", sa.Numeric(38, 18), nullable=True),
        sa.Column("fee_currency", sa.Text(), nullable=True),
        sa.Column("rebate_amount", sa.Numeric(38, 18), nullable=True),
        sa.Column("rebate_currency", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trade_id", sa.Text(), nullable=True),
        sa.Column("source_event_id", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("exchange_occurred_at", "fill_id", name="pk_fills"),
        sa.CheckConstraint("quantity > 0", name=op.f(FILLS_QUANTITY_CHECK_NAME)),
        schema=SCHEMA_NAME,
        postgresql_partition_by="RANGE (exchange_occurred_at)",
    )
    op.create_index(
        FILLS_ORDER_TIME_INDEX_NAME,
        FILLS_TABLE_NAME,
        ["order_id", "exchange_occurred_at"],
        schema=SCHEMA_NAME,
    )
    op.create_index(
        FILLS_ACCOUNT_TIME_INDEX_NAME,
        FILLS_TABLE_NAME,
        ["exchange", "account_id", sa.text("exchange_occurred_at DESC")],
        schema=SCHEMA_NAME,
    )
    op.create_table(
        FILL_IDS_TABLE_NAME,
        sa.Column("exchange", sa.Text(), nullable=False),
        sa.Column("account_id", sa.Text(), nullable=False),
        sa.Column("exchange_fill_id", sa.Text(), nullable=False),
        sa.Column("fill_id", sa.Text(), nullable=False),
        sa.Column("exchange_occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint(
            "exchange",
            "account_id",
            "exchange_fill_id",
            name="pk_fill_ids",
        ),
        sa.UniqueConstraint("fill_id", name=op.f(FILL_IDS_FILL_ID_UNIQUE_NAME)),
        schema=SCHEMA_NAME,
    )


def downgrade() -> None:
    """Drop append-only fill storage and fill idempotency registry."""

    op.drop_table(FILL_IDS_TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_index(FILLS_ACCOUNT_TIME_INDEX_NAME, table_name=FILLS_TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_index(FILLS_ORDER_TIME_INDEX_NAME, table_name=FILLS_TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_table(FILLS_TABLE_NAME, schema=SCHEMA_NAME)
