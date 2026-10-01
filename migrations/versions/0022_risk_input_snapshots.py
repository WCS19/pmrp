"""Create risk input snapshot table.

Revision ID: 0022_risk_input_snapshots
Revises: 0021_health_audit_tables
Create Date: 2026-10-01

Lock risk: low on empty databases; creates one unpartitioned table and three
indexes in pmrp_risk.
Expected runtime: under one second on empty local and CI PostgreSQL databases.
Rollback plan: downgrade drops risk_input_snapshots.
Backfill plan: not applicable; no rows are created or transformed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_risk_input_snapshots"
down_revision: str | None = "0021_health_audit_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_NAME = "pmrp_risk"
RISK_INPUT_SNAPSHOTS_TABLE_NAME = "risk_input_snapshots"
RISK_INPUT_SNAPSHOTS_STRATEGY_TIME_INDEX_NAME = "ix_risk_input_snapshots__strategy_time"
RISK_INPUT_SNAPSHOTS_ACCOUNT_MARKET_TIME_INDEX_NAME = "ix_risk_input_snapshots__account_market_time"
RISK_INPUT_SNAPSHOTS_PAYLOAD_HASH_INDEX_NAME = "ix_risk_input_snapshots__payload_hash"
RISK_INPUT_SNAPSHOTS_OPEN_ORDER_QUANTITY_CHECK_NAME = "ck_risk_input_snapshots__open_order_quantity"
RISK_INPUT_SNAPSHOTS_AVAILABLE_BALANCE_CHECK_NAME = "ck_risk_input_snapshots__available_balance"
RISK_INPUT_SNAPSHOTS_GROSS_EXPOSURE_CHECK_NAME = "ck_risk_input_snapshots__gross_exposure"
RISK_INPUT_SNAPSHOTS_MARKET_DATA_AGE_CHECK_NAME = "ck_risk_input_snapshots__market_data_age"


def upgrade() -> None:
    """Create durable canonical risk input snapshot storage."""

    op.create_table(
        RISK_INPUT_SNAPSHOTS_TABLE_NAME,
        sa.Column("risk_input_snapshot_id", sa.Text(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("strategy_id", sa.Text(), nullable=False),
        sa.Column("exchange", sa.Text(), nullable=False),
        sa.Column("account_id", sa.Text(), nullable=False),
        sa.Column("market_id", sa.Text(), nullable=False),
        sa.Column("current_position", sa.Numeric(38, 18), nullable=False),
        sa.Column("open_order_quantity", sa.Numeric(38, 18), nullable=False),
        sa.Column("available_balance", sa.Numeric(38, 18), nullable=False),
        sa.Column("gross_exposure", sa.Numeric(38, 18), nullable=False),
        sa.Column("net_exposure", sa.Numeric(38, 18), nullable=False),
        sa.Column("daily_realized_pnl", sa.Numeric(38, 18), nullable=False),
        sa.Column("daily_unrealized_pnl", sa.Numeric(38, 18), nullable=False),
        sa.Column("market_data_age_ms", sa.BigInteger(), nullable=False),
        sa.Column("reconciliation_healthy", sa.Boolean(), nullable=False),
        sa.Column("kill_switch_clear", sa.Boolean(), nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint(
            "risk_input_snapshot_id",
            name="pk_risk_input_snapshots",
        ),
        sa.CheckConstraint(
            "open_order_quantity >= 0",
            name=op.f(RISK_INPUT_SNAPSHOTS_OPEN_ORDER_QUANTITY_CHECK_NAME),
        ),
        sa.CheckConstraint(
            "available_balance >= 0",
            name=op.f(RISK_INPUT_SNAPSHOTS_AVAILABLE_BALANCE_CHECK_NAME),
        ),
        sa.CheckConstraint(
            "gross_exposure >= 0",
            name=op.f(RISK_INPUT_SNAPSHOTS_GROSS_EXPOSURE_CHECK_NAME),
        ),
        sa.CheckConstraint(
            "market_data_age_ms >= 0",
            name=op.f(RISK_INPUT_SNAPSHOTS_MARKET_DATA_AGE_CHECK_NAME),
        ),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        RISK_INPUT_SNAPSHOTS_STRATEGY_TIME_INDEX_NAME,
        RISK_INPUT_SNAPSHOTS_TABLE_NAME,
        ["strategy_id", sa.text("captured_at DESC")],
        schema=SCHEMA_NAME,
    )
    op.create_index(
        RISK_INPUT_SNAPSHOTS_ACCOUNT_MARKET_TIME_INDEX_NAME,
        RISK_INPUT_SNAPSHOTS_TABLE_NAME,
        ["exchange", "account_id", "market_id", sa.text("captured_at DESC")],
        schema=SCHEMA_NAME,
    )
    op.create_index(
        RISK_INPUT_SNAPSHOTS_PAYLOAD_HASH_INDEX_NAME,
        RISK_INPUT_SNAPSHOTS_TABLE_NAME,
        ["payload_hash"],
        schema=SCHEMA_NAME,
    )


def downgrade() -> None:
    """Drop durable canonical risk input snapshot storage."""

    op.drop_index(
        RISK_INPUT_SNAPSHOTS_PAYLOAD_HASH_INDEX_NAME,
        table_name=RISK_INPUT_SNAPSHOTS_TABLE_NAME,
        schema=SCHEMA_NAME,
    )
    op.drop_index(
        RISK_INPUT_SNAPSHOTS_ACCOUNT_MARKET_TIME_INDEX_NAME,
        table_name=RISK_INPUT_SNAPSHOTS_TABLE_NAME,
        schema=SCHEMA_NAME,
    )
    op.drop_index(
        RISK_INPUT_SNAPSHOTS_STRATEGY_TIME_INDEX_NAME,
        table_name=RISK_INPUT_SNAPSHOTS_TABLE_NAME,
        schema=SCHEMA_NAME,
    )
    op.drop_table(RISK_INPUT_SNAPSHOTS_TABLE_NAME, schema=SCHEMA_NAME)
