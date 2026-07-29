"""Create PnL attribution and settlement tables.

Revision ID: 0015_pnl_settlements
Revises: 0014_portfolio_storage
Create Date: 2026-07-29

Lock risk: low on empty databases; creates two unpartitioned tables and two
indexes in pmrp_portfolio.
Expected runtime: under one second on empty local and CI PostgreSQL databases.
Rollback plan: downgrade drops settlements, then pnl_attributions.
Backfill plan: not applicable; no rows are created or transformed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_pnl_settlements"
down_revision: str | None = "0014_portfolio_storage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_NAME = "pmrp_portfolio"
PNL_ATTRIBUTIONS_TABLE_NAME = "pnl_attributions"
SETTLEMENTS_TABLE_NAME = "settlements"
PNL_ATTRIBUTIONS_STRATEGY_PERIOD_INDEX_NAME = "ix_pnl_attributions__strategy_period"
SETTLEMENTS_MARKET_CREATED_INDEX_NAME = "ix_settlements__market_created"
SETTLEMENTS_CORRECTION_FOREIGN_KEY_NAME = "fk_settlements__correction_of_settlement_id__settlements"


def upgrade() -> None:
    """Create versioned PnL attribution and settlement lifecycle storage."""

    op.create_table(
        PNL_ATTRIBUTIONS_TABLE_NAME,
        sa.Column("attribution_id", sa.Text(), nullable=False),
        sa.Column("strategy_id", sa.Text(), nullable=True),
        sa.Column("market_id", sa.Text(), nullable=True),
        sa.Column("exchange", sa.Text(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("realized_trading_pnl", sa.Numeric(38, 18), nullable=False),
        sa.Column("unrealized_pnl_change", sa.Numeric(38, 18), nullable=False),
        sa.Column("fees", sa.Numeric(38, 18), nullable=False),
        sa.Column("rebates", sa.Numeric(38, 18), nullable=False),
        sa.Column("slippage", sa.Numeric(38, 18), nullable=True),
        sa.Column("settlement_pnl", sa.Numeric(38, 18), nullable=True),
        sa.Column("total_pnl", sa.Numeric(38, 18), nullable=False),
        sa.Column("calculation_version", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("attribution_id", name="pk_pnl_attributions"),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        PNL_ATTRIBUTIONS_STRATEGY_PERIOD_INDEX_NAME,
        PNL_ATTRIBUTIONS_TABLE_NAME,
        ["strategy_id", "starts_at", "ends_at"],
        schema=SCHEMA_NAME,
    )
    op.create_table(
        SETTLEMENTS_TABLE_NAME,
        sa.Column("settlement_id", sa.Text(), nullable=False),
        sa.Column("market_id", sa.Text(), nullable=False),
        sa.Column("exchange", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "winning_outcome_ids",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payout_per_unit", sa.Numeric(38, 18), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_reference", sa.Text(), nullable=True),
        sa.Column("correction_of_settlement_id", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("settlement_id", name="pk_settlements"),
        sa.ForeignKeyConstraint(
            ["correction_of_settlement_id"],
            [f"{SCHEMA_NAME}.{SETTLEMENTS_TABLE_NAME}.settlement_id"],
            name=op.f(SETTLEMENTS_CORRECTION_FOREIGN_KEY_NAME),
        ),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        SETTLEMENTS_MARKET_CREATED_INDEX_NAME,
        SETTLEMENTS_TABLE_NAME,
        ["market_id", sa.text("created_at DESC")],
        schema=SCHEMA_NAME,
    )


def downgrade() -> None:
    """Drop versioned PnL attribution and settlement lifecycle storage."""

    op.drop_index(
        SETTLEMENTS_MARKET_CREATED_INDEX_NAME,
        table_name=SETTLEMENTS_TABLE_NAME,
        schema=SCHEMA_NAME,
    )
    op.drop_table(SETTLEMENTS_TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_index(
        PNL_ATTRIBUTIONS_STRATEGY_PERIOD_INDEX_NAME,
        table_name=PNL_ATTRIBUTIONS_TABLE_NAME,
        schema=SCHEMA_NAME,
    )
    op.drop_table(PNL_ATTRIBUTIONS_TABLE_NAME, schema=SCHEMA_NAME)
