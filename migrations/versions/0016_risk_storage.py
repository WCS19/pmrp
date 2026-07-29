"""Create risk limit, decision, and breach tables.

Revision ID: 0016_risk_storage
Revises: 0015_pnl_settlements
Create Date: 2026-07-29

Lock risk: low on empty databases; creates two unpartitioned tables, one
partitioned table, and four indexes in pmrp_risk.
Expected runtime: under one second on empty local and CI PostgreSQL databases.
Rollback plan: downgrade drops risk_breaches, risk_decisions, then risk_limits.
Backfill plan: not applicable; no rows are created or transformed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_risk_storage"
down_revision: str | None = "0015_pnl_settlements"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_NAME = "pmrp_risk"
RISK_LIMITS_TABLE_NAME = "risk_limits"
RISK_DECISIONS_TABLE_NAME = "risk_decisions"
RISK_BREACHES_TABLE_NAME = "risk_breaches"
RISK_LIMITS_ACTIVE_SCOPE_INDEX_NAME = "ix_risk_limits__active_scope"
RISK_DECISIONS_INTENT_INDEX_NAME = "ix_risk_decisions__intent"
RISK_DECISIONS_STATUS_TIME_INDEX_NAME = "ix_risk_decisions__status_time"
RISK_BREACHES_OPEN_SEVERITY_INDEX_NAME = "ix_risk_breaches__open_severity"


def upgrade() -> None:
    """Create durable risk policy, decision, and breach storage."""

    op.create_table(
        RISK_LIMITS_TABLE_NAME,
        sa.Column("risk_limit_id", sa.Text(), nullable=False),
        sa.Column("rule_id", sa.Text(), nullable=False),
        sa.Column("rule_version", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("scope_id", sa.Text(), nullable=True),
        sa.Column("limit_type", sa.Text(), nullable=False),
        sa.Column("limit_value", sa.Numeric(38, 18), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("approved_by", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "aggregate_version",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.PrimaryKeyConstraint("risk_limit_id", name="pk_risk_limits"),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        RISK_LIMITS_ACTIVE_SCOPE_INDEX_NAME,
        RISK_LIMITS_TABLE_NAME,
        ["scope", "scope_id", "rule_id"],
        schema=SCHEMA_NAME,
        postgresql_where=sa.text("enabled = true"),
    )
    op.create_table(
        RISK_DECISIONS_TABLE_NAME,
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("risk_decision_id", sa.Text(), nullable=False),
        sa.Column("intent_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("input_snapshot_id", sa.Text(), nullable=False),
        sa.Column("approved_quantity", sa.Numeric(38, 18), nullable=True),
        sa.Column("approved_limit_price", sa.Numeric(38, 18), nullable=True),
        sa.Column("approval_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("configuration_hash", sa.Text(), nullable=False),
        sa.Column("correlation_id", sa.Text(), nullable=False),
        sa.Column("rule_results", postgresql.JSONB(), nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("evaluated_at", "risk_decision_id", name="pk_risk_decisions"),
        schema=SCHEMA_NAME,
        postgresql_partition_by="RANGE (evaluated_at)",
    )
    op.create_index(
        RISK_DECISIONS_INTENT_INDEX_NAME,
        RISK_DECISIONS_TABLE_NAME,
        ["intent_id"],
        schema=SCHEMA_NAME,
    )
    op.create_index(
        RISK_DECISIONS_STATUS_TIME_INDEX_NAME,
        RISK_DECISIONS_TABLE_NAME,
        ["status", sa.text("evaluated_at DESC")],
        schema=SCHEMA_NAME,
    )
    op.create_table(
        RISK_BREACHES_TABLE_NAME,
        sa.Column("breach_id", sa.Text(), nullable=False),
        sa.Column("rule_id", sa.Text(), nullable=False),
        sa.Column("rule_version", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("scope_id", sa.Text(), nullable=True),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_value", sa.Numeric(38, 18), nullable=True),
        sa.Column("limit_value", sa.Numeric(38, 18), nullable=True),
        sa.Column("unit", sa.Text(), nullable=True),
        sa.Column("action_taken", sa.Text(), nullable=False),
        sa.Column("correlation_id", sa.Text(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("breach_id", name="pk_risk_breaches"),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        RISK_BREACHES_OPEN_SEVERITY_INDEX_NAME,
        RISK_BREACHES_TABLE_NAME,
        ["severity", sa.text("detected_at DESC")],
        schema=SCHEMA_NAME,
        postgresql_where=sa.text("resolved_at IS NULL"),
    )


def downgrade() -> None:
    """Drop durable risk policy, decision, and breach storage."""

    op.drop_index(
        RISK_BREACHES_OPEN_SEVERITY_INDEX_NAME,
        table_name=RISK_BREACHES_TABLE_NAME,
        schema=SCHEMA_NAME,
    )
    op.drop_table(RISK_BREACHES_TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_index(
        RISK_DECISIONS_STATUS_TIME_INDEX_NAME,
        table_name=RISK_DECISIONS_TABLE_NAME,
        schema=SCHEMA_NAME,
    )
    op.drop_index(
        RISK_DECISIONS_INTENT_INDEX_NAME,
        table_name=RISK_DECISIONS_TABLE_NAME,
        schema=SCHEMA_NAME,
    )
    op.drop_table(RISK_DECISIONS_TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_index(
        RISK_LIMITS_ACTIVE_SCOPE_INDEX_NAME,
        table_name=RISK_LIMITS_TABLE_NAME,
        schema=SCHEMA_NAME,
    )
    op.drop_table(RISK_LIMITS_TABLE_NAME, schema=SCHEMA_NAME)
