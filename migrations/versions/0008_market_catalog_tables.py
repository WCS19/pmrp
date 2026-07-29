"""Create market catalog tables.

Revision ID: 0008_market_catalog_tables
Revises: 0007_idempotency_dead_letters
Create Date: 2026-07-29

Lock risk: low on empty databases; creates three unpartitioned tables and five
indexes in pmrp_market.
Expected runtime: under one second on empty local and CI PostgreSQL databases.
Rollback plan: downgrade drops contracts, outcomes, then markets.
Backfill plan: not applicable; no rows are created or transformed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_market_catalog_tables"
down_revision: str | None = "0007_idempotency_dead_letters"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_NAME = "pmrp_market"
MARKETS_TABLE_NAME = "markets"
OUTCOMES_TABLE_NAME = "outcomes"
CONTRACTS_TABLE_NAME = "contracts"
MARKETS_EXCHANGE_STATUS_INDEX_NAME = "ix_markets__exchange_status"
MARKETS_STATUS_CLOSES_INDEX_NAME = "ix_markets__status_closes"
MARKETS_UPDATED_INDEX_NAME = "ix_markets__updated"
OUTCOMES_MARKET_INDEX_NAME = "ix_outcomes__market"
CONTRACTS_MARKET_ACTIVE_INDEX_NAME = "ix_contracts__market_active"
MARKETS_EXCHANGE_MARKET_UNIQUE_NAME = "uq_markets__exchange_exchange_market_id"
OUTCOMES_MARKET_OUTCOME_INDEX_UNIQUE_NAME = "uq_outcomes__market_id_outcome_index"
OUTCOMES_MARKET_NORMALIZED_NAME_UNIQUE_NAME = "uq_outcomes__market_id_normalized_name"
CONTRACTS_MARKET_OUTCOME_UNIQUE_NAME = "uq_contracts__market_id_outcome_id"
OUTCOMES_MARKET_FOREIGN_KEY_NAME = "fk_outcomes__market_id__markets"
CONTRACTS_MARKET_FOREIGN_KEY_NAME = "fk_contracts__market_id__markets"
CONTRACTS_OUTCOME_FOREIGN_KEY_NAME = "fk_contracts__outcome_id__outcomes"
MARKETS_PAYOUT_CHECK_NAME = "ck_markets__payout_per_unit"
MARKETS_TICK_SIZE_CHECK_NAME = "ck_markets__tick_size"
MARKETS_QUANTITY_INCREMENT_CHECK_NAME = "ck_markets__quantity_increment"


def upgrade() -> None:
    """Create canonical market catalog storage tables."""

    op.create_table(
        MARKETS_TABLE_NAME,
        sa.Column("market_id", sa.Text(), nullable=False),
        sa.Column("exchange", sa.Text(), nullable=False),
        sa.Column("exchange_market_id", sa.Text(), nullable=False),
        sa.Column("exchange_event_id", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("subtitle", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("outcome_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("opens_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolves_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("payout_per_unit", sa.Numeric(38, 18), nullable=False),
        sa.Column("tick_size", sa.Numeric(38, 18), nullable=False),
        sa.Column("quantity_increment", sa.Numeric(38, 18), nullable=False),
        sa.Column("rules_text", sa.Text(), nullable=True),
        sa.Column("rules_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "aggregate_version",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.PrimaryKeyConstraint("market_id", name="pk_markets"),
        sa.UniqueConstraint(
            "exchange",
            "exchange_market_id",
            name=op.f(MARKETS_EXCHANGE_MARKET_UNIQUE_NAME),
        ),
        sa.CheckConstraint("payout_per_unit > 0", name=op.f(MARKETS_PAYOUT_CHECK_NAME)),
        sa.CheckConstraint("tick_size > 0", name=op.f(MARKETS_TICK_SIZE_CHECK_NAME)),
        sa.CheckConstraint(
            "quantity_increment > 0",
            name=op.f(MARKETS_QUANTITY_INCREMENT_CHECK_NAME),
        ),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        MARKETS_EXCHANGE_STATUS_INDEX_NAME,
        MARKETS_TABLE_NAME,
        ["exchange", "status"],
        schema=SCHEMA_NAME,
    )
    op.create_index(
        MARKETS_STATUS_CLOSES_INDEX_NAME,
        MARKETS_TABLE_NAME,
        ["status", "closes_at"],
        schema=SCHEMA_NAME,
    )
    op.create_index(
        MARKETS_UPDATED_INDEX_NAME,
        MARKETS_TABLE_NAME,
        [sa.text("updated_at DESC"), "market_id"],
        schema=SCHEMA_NAME,
    )
    op.create_table(
        OUTCOMES_TABLE_NAME,
        sa.Column("outcome_id", sa.Text(), nullable=False),
        sa.Column("market_id", sa.Text(), nullable=False),
        sa.Column("exchange_outcome_id", sa.Text(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False),
        sa.Column("outcome_index", sa.Integer(), nullable=False),
        sa.Column("is_tradeable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_winning", sa.Boolean(), nullable=True),
        sa.Column("payout_per_unit", sa.Numeric(38, 18), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("outcome_id", name="pk_outcomes"),
        sa.ForeignKeyConstraint(
            ["market_id"],
            [f"{SCHEMA_NAME}.{MARKETS_TABLE_NAME}.market_id"],
            name=op.f(OUTCOMES_MARKET_FOREIGN_KEY_NAME),
        ),
        sa.UniqueConstraint(
            "market_id",
            "outcome_index",
            name=op.f(OUTCOMES_MARKET_OUTCOME_INDEX_UNIQUE_NAME),
        ),
        sa.UniqueConstraint(
            "market_id",
            "normalized_name",
            name=op.f(OUTCOMES_MARKET_NORMALIZED_NAME_UNIQUE_NAME),
        ),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        OUTCOMES_MARKET_INDEX_NAME,
        OUTCOMES_TABLE_NAME,
        ["market_id", "outcome_index"],
        schema=SCHEMA_NAME,
    )
    op.create_table(
        CONTRACTS_TABLE_NAME,
        sa.Column("contract_id", sa.Text(), nullable=False),
        sa.Column("market_id", sa.Text(), nullable=False),
        sa.Column("outcome_id", sa.Text(), nullable=False),
        sa.Column("exchange_contract_id", sa.Text(), nullable=True),
        sa.Column("symbol", sa.Text(), nullable=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("tick_size", sa.Numeric(38, 18), nullable=False),
        sa.Column("quantity_increment", sa.Numeric(38, 18), nullable=False),
        sa.Column("min_order_quantity", sa.Numeric(38, 18), nullable=True),
        sa.Column("max_order_quantity", sa.Numeric(38, 18), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("contract_id", name="pk_contracts"),
        sa.ForeignKeyConstraint(
            ["market_id"],
            [f"{SCHEMA_NAME}.{MARKETS_TABLE_NAME}.market_id"],
            name=op.f(CONTRACTS_MARKET_FOREIGN_KEY_NAME),
        ),
        sa.ForeignKeyConstraint(
            ["outcome_id"],
            [f"{SCHEMA_NAME}.{OUTCOMES_TABLE_NAME}.outcome_id"],
            name=op.f(CONTRACTS_OUTCOME_FOREIGN_KEY_NAME),
        ),
        sa.UniqueConstraint(
            "market_id",
            "outcome_id",
            name=op.f(CONTRACTS_MARKET_OUTCOME_UNIQUE_NAME),
        ),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        CONTRACTS_MARKET_ACTIVE_INDEX_NAME,
        CONTRACTS_TABLE_NAME,
        ["market_id", "active"],
        schema=SCHEMA_NAME,
    )


def downgrade() -> None:
    """Drop canonical market catalog storage tables."""

    op.drop_index(
        CONTRACTS_MARKET_ACTIVE_INDEX_NAME, table_name=CONTRACTS_TABLE_NAME, schema=SCHEMA_NAME
    )
    op.drop_table(CONTRACTS_TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_index(OUTCOMES_MARKET_INDEX_NAME, table_name=OUTCOMES_TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_table(OUTCOMES_TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_index(MARKETS_UPDATED_INDEX_NAME, table_name=MARKETS_TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_index(
        MARKETS_STATUS_CLOSES_INDEX_NAME,
        table_name=MARKETS_TABLE_NAME,
        schema=SCHEMA_NAME,
    )
    op.drop_index(
        MARKETS_EXCHANGE_STATUS_INDEX_NAME,
        table_name=MARKETS_TABLE_NAME,
        schema=SCHEMA_NAME,
    )
    op.drop_table(MARKETS_TABLE_NAME, schema=SCHEMA_NAME)
