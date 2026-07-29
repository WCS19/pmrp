"""Create kill switch and capital reservation tables.

Revision ID: 0017_kill_switch_reservations
Revises: 0016_risk_storage
Create Date: 2026-07-29

Lock risk: low on empty databases; creates two unpartitioned tables and two
indexes in pmrp_risk.
Expected runtime: under one second on empty local and CI PostgreSQL databases.
Rollback plan: downgrade drops capital_reservations, then kill_switches.
Backfill plan: not applicable; no rows are created or transformed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_kill_switch_reservations"
down_revision: str | None = "0016_risk_storage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_NAME = "pmrp_risk"
KILL_SWITCHES_TABLE_NAME = "kill_switches"
CAPITAL_RESERVATIONS_TABLE_NAME = "capital_reservations"
KILL_SWITCHES_ACTIVE_SCOPE_INDEX_NAME = "uq_kill_switches__active_scope"
CAPITAL_RESERVATIONS_ACTIVE_EXPIRY_INDEX_NAME = "ix_capital_reservations__active_expiry"
CAPITAL_RESERVATIONS_INTENT_UNIQUE_NAME = "uq_capital_reservations__intent_id"


def upgrade() -> None:
    """Create scoped trading gate and capital reservation storage."""

    op.create_table(
        KILL_SWITCHES_TABLE_NAME,
        sa.Column("kill_switch_id", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("scope_id", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_by", sa.Text(), nullable=True),
        sa.Column("activation_reason", sa.Text(), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_by", sa.Text(), nullable=True),
        sa.Column("release_reason", sa.Text(), nullable=True),
        sa.Column(
            "aggregate_version",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("kill_switch_id", name="pk_kill_switches"),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        KILL_SWITCHES_ACTIVE_SCOPE_INDEX_NAME,
        KILL_SWITCHES_TABLE_NAME,
        ["scope", sa.text("COALESCE(scope_id, '')")],
        unique=True,
        schema=SCHEMA_NAME,
        postgresql_where=sa.text("active = true"),
    )
    op.create_table(
        CAPITAL_RESERVATIONS_TABLE_NAME,
        sa.Column("reservation_id", sa.Text(), nullable=False),
        sa.Column("intent_id", sa.Text(), nullable=False),
        sa.Column("strategy_id", sa.Text(), nullable=False),
        sa.Column("exchange", sa.Text(), nullable=False),
        sa.Column("account_id", sa.Text(), nullable=False),
        sa.Column("market_id", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Numeric(38, 18), nullable=False),
        sa.Column("notional", sa.Numeric(38, 18), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("reservation_id", name="pk_capital_reservations"),
        sa.UniqueConstraint(
            "intent_id",
            name=op.f(CAPITAL_RESERVATIONS_INTENT_UNIQUE_NAME),
        ),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        CAPITAL_RESERVATIONS_ACTIVE_EXPIRY_INDEX_NAME,
        CAPITAL_RESERVATIONS_TABLE_NAME,
        ["expires_at"],
        schema=SCHEMA_NAME,
        postgresql_where=sa.text("released_at IS NULL"),
    )


def downgrade() -> None:
    """Drop scoped trading gate and capital reservation storage."""

    op.drop_index(
        CAPITAL_RESERVATIONS_ACTIVE_EXPIRY_INDEX_NAME,
        table_name=CAPITAL_RESERVATIONS_TABLE_NAME,
        schema=SCHEMA_NAME,
    )
    op.drop_table(CAPITAL_RESERVATIONS_TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_index(
        KILL_SWITCHES_ACTIVE_SCOPE_INDEX_NAME,
        table_name=KILL_SWITCHES_TABLE_NAME,
        schema=SCHEMA_NAME,
    )
    op.drop_table(KILL_SWITCHES_TABLE_NAME, schema=SCHEMA_NAME)
