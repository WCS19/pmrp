"""Create signal history and feature snapshot tables.

Revision ID: 0011_signals_features
Revises: 0010_strategy_model_metadata
Create Date: 2026-07-29

Lock risk: low on empty databases; creates two partitioned tables and three
indexes in pmrp_research.
Expected runtime: under one second on empty local and CI PostgreSQL databases.
Rollback plan: downgrade drops feature_snapshots, then signals.
Backfill plan: not applicable; no rows are created or transformed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_signals_features"
down_revision: str | None = "0010_strategy_model_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_NAME = "pmrp_research"
SIGNALS_TABLE_NAME = "signals"
FEATURE_SNAPSHOTS_TABLE_NAME = "feature_snapshots"
SIGNALS_STRATEGY_TIME_INDEX_NAME = "ix_signals__strategy_time"
SIGNALS_MARKET_TIME_INDEX_NAME = "ix_signals__market_time"
FEATURE_SNAPSHOTS_MARKET_TIME_INDEX_NAME = "ix_feature_snapshots__market_time"
SIGNALS_FAIR_PROBABILITY_CHECK_NAME = "ck_signals__fair_probability"


def upgrade() -> None:
    """Create append-only signal history and feature snapshot storage."""

    op.create_table(
        SIGNALS_TABLE_NAME,
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signal_id", sa.Text(), nullable=False),
        sa.Column("strategy_id", sa.Text(), nullable=False),
        sa.Column("market_id", sa.Text(), nullable=False),
        sa.Column("contract_id", sa.Text(), nullable=True),
        sa.Column("outcome_id", sa.Text(), nullable=True),
        sa.Column("signal_type", sa.Text(), nullable=False),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column("strength", sa.Numeric(38, 18), nullable=True),
        sa.Column("fair_probability", sa.Numeric(38, 18), nullable=True),
        sa.Column("confidence", sa.Numeric(38, 18), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model_id", sa.Text(), nullable=True),
        sa.Column("model_version", sa.Text(), nullable=True),
        sa.Column("feature_snapshot_id", sa.Text(), nullable=True),
        sa.Column("reason_code", sa.Text(), nullable=False),
        sa.Column("reason_text", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.Text(), nullable=False),
        sa.Column("source_event_id", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("generated_at", "signal_id", name="pk_signals"),
        sa.CheckConstraint(
            "fair_probability IS NULL OR (fair_probability >= 0 AND fair_probability <= 1)",
            name=op.f(SIGNALS_FAIR_PROBABILITY_CHECK_NAME),
        ),
        schema=SCHEMA_NAME,
        postgresql_partition_by="RANGE (generated_at)",
    )
    op.create_index(
        SIGNALS_STRATEGY_TIME_INDEX_NAME,
        SIGNALS_TABLE_NAME,
        ["strategy_id", sa.text("generated_at DESC")],
        schema=SCHEMA_NAME,
    )
    op.create_index(
        SIGNALS_MARKET_TIME_INDEX_NAME,
        SIGNALS_TABLE_NAME,
        ["market_id", sa.text("generated_at DESC")],
        schema=SCHEMA_NAME,
    )
    op.create_table(
        FEATURE_SNAPSHOTS_TABLE_NAME,
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("feature_snapshot_id", sa.Text(), nullable=False),
        sa.Column("market_id", sa.Text(), nullable=False),
        sa.Column("strategy_id", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("calculation_version", sa.Text(), nullable=False),
        sa.Column("features", postgresql.JSONB(), nullable=False),
        sa.Column("source_event_ids", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint(
            "observed_at",
            "feature_snapshot_id",
            name="pk_feature_snapshots",
        ),
        schema=SCHEMA_NAME,
        postgresql_partition_by="RANGE (observed_at)",
    )
    op.create_index(
        FEATURE_SNAPSHOTS_MARKET_TIME_INDEX_NAME,
        FEATURE_SNAPSHOTS_TABLE_NAME,
        ["market_id", sa.text("observed_at DESC")],
        schema=SCHEMA_NAME,
    )


def downgrade() -> None:
    """Drop append-only signal history and feature snapshot storage."""

    op.drop_index(
        FEATURE_SNAPSHOTS_MARKET_TIME_INDEX_NAME,
        table_name=FEATURE_SNAPSHOTS_TABLE_NAME,
        schema=SCHEMA_NAME,
    )
    op.drop_table(FEATURE_SNAPSHOTS_TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_index(SIGNALS_MARKET_TIME_INDEX_NAME, table_name=SIGNALS_TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_index(
        SIGNALS_STRATEGY_TIME_INDEX_NAME,
        table_name=SIGNALS_TABLE_NAME,
        schema=SCHEMA_NAME,
    )
    op.drop_table(SIGNALS_TABLE_NAME, schema=SCHEMA_NAME)
