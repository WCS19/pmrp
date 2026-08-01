"""Create reconciliation run and mismatch tables.

Revision ID: 0018_reconciliation_tables
Revises: 0017_kill_switch_reservations
Create Date: 2026-07-29

Lock risk: low on empty databases; creates two unpartitioned tables and two
indexes in pmrp_ops.
Expected runtime: under one second on empty local and CI PostgreSQL databases.
Rollback plan: downgrade drops reconciliation_mismatches, then reconciliation_runs.
Backfill plan: not applicable; no rows are created or transformed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_reconciliation_tables"
down_revision: str | None = "0017_kill_switch_reservations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_NAME = "pmrp_ops"
RECONCILIATION_RUNS_TABLE_NAME = "reconciliation_runs"
RECONCILIATION_MISMATCHES_TABLE_NAME = "reconciliation_mismatches"
RECONCILIATION_RUNS_ACCOUNT_TIME_INDEX_NAME = "ix_reconciliation_runs__account_time"
RECONCILIATION_MISMATCHES_RUN_INDEX_NAME = "ix_reconciliation_mismatches__run"
RECONCILIATION_MISMATCHES_RUN_FOREIGN_KEY_NAME = "fk_reconciliation_mismatches__reconciliation_runs"


def upgrade() -> None:
    """Create durable account reconciliation lifecycle storage."""

    op.create_table(
        RECONCILIATION_RUNS_TABLE_NAME,
        sa.Column("reconciliation_id", sa.Text(), nullable=False),
        sa.Column("exchange", sa.Text(), nullable=False),
        sa.Column("account_id", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "open_orders_checked",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "positions_checked",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "balances_checked",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "fills_checked",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "trading_gate_released",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("initiated_by", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("reconciliation_id", name="pk_reconciliation_runs"),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        RECONCILIATION_RUNS_ACCOUNT_TIME_INDEX_NAME,
        RECONCILIATION_RUNS_TABLE_NAME,
        ["exchange", "account_id", sa.text("started_at DESC")],
        schema=SCHEMA_NAME,
    )
    op.create_table(
        RECONCILIATION_MISMATCHES_TABLE_NAME,
        sa.Column("mismatch_id", sa.Text(), nullable=False),
        sa.Column("reconciliation_id", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("local_value", sa.Text(), nullable=True),
        sa.Column("external_value", sa.Text(), nullable=True),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("requires_manual_review", sa.Boolean(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("mismatch_id", name="pk_reconciliation_mismatches"),
        sa.ForeignKeyConstraint(
            ["reconciliation_id"],
            [f"{SCHEMA_NAME}.{RECONCILIATION_RUNS_TABLE_NAME}.reconciliation_id"],
            name=op.f(RECONCILIATION_MISMATCHES_RUN_FOREIGN_KEY_NAME),
        ),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        RECONCILIATION_MISMATCHES_RUN_INDEX_NAME,
        RECONCILIATION_MISMATCHES_TABLE_NAME,
        ["reconciliation_id", "severity"],
        schema=SCHEMA_NAME,
    )


def downgrade() -> None:
    """Drop durable account reconciliation lifecycle storage."""

    op.drop_index(
        RECONCILIATION_MISMATCHES_RUN_INDEX_NAME,
        table_name=RECONCILIATION_MISMATCHES_TABLE_NAME,
        schema=SCHEMA_NAME,
    )
    op.drop_table(RECONCILIATION_MISMATCHES_TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_index(
        RECONCILIATION_RUNS_ACCOUNT_TIME_INDEX_NAME,
        table_name=RECONCILIATION_RUNS_TABLE_NAME,
        schema=SCHEMA_NAME,
    )
    op.drop_table(RECONCILIATION_RUNS_TABLE_NAME, schema=SCHEMA_NAME)
