"""Create adapter health and operator audit tables.

Revision ID: 0021_health_audit_tables
Revises: 0020_market_relationships
Create Date: 2026-08-01

Lock risk: low on empty databases; creates two partitioned tables and three
indexes across pmrp_ops and pmrp_audit.
Expected runtime: under one second on empty local and CI PostgreSQL databases.
Rollback plan: downgrade drops operator_audit_records, then
adapter_health_snapshots.
Backfill plan: not applicable; no rows are created or transformed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_health_audit_tables"
down_revision: str | None = "0020_market_relationships"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OPS_SCHEMA_NAME = "pmrp_ops"
AUDIT_SCHEMA_NAME = "pmrp_audit"
ADAPTER_HEALTH_SNAPSHOTS_TABLE_NAME = "adapter_health_snapshots"
OPERATOR_AUDIT_RECORDS_TABLE_NAME = "operator_audit_records"
ADAPTER_HEALTH_EXCHANGE_TIME_INDEX_NAME = "ix_adapter_health__exchange_time"
OPERATOR_AUDIT_ACTOR_TIME_INDEX_NAME = "ix_operator_audit__actor_time"
OPERATOR_AUDIT_SCOPE_TIME_INDEX_NAME = "ix_operator_audit__scope_time"


def upgrade() -> None:
    """Create adapter health and operator audit storage."""

    op.create_table(
        ADAPTER_HEALTH_SNAPSHOTS_TABLE_NAME,
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exchange", sa.Text(), nullable=False),
        sa.Column("environment", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("connected", sa.Boolean(), nullable=False),
        sa.Column("authenticated", sa.Boolean(), nullable=False),
        sa.Column("subscriptions_active", sa.Boolean(), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_reconciliation_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("market_data_fresh", sa.Boolean(), nullable=False),
        sa.Column("trading_gate_open", sa.Boolean(), nullable=False),
        sa.Column("reconnect_attempts", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint(
            "captured_at",
            "exchange",
            "environment",
            name="pk_adapter_health_snapshots",
        ),
        schema=OPS_SCHEMA_NAME,
        postgresql_partition_by="RANGE (captured_at)",
    )
    op.create_index(
        ADAPTER_HEALTH_EXCHANGE_TIME_INDEX_NAME,
        ADAPTER_HEALTH_SNAPSHOTS_TABLE_NAME,
        ["exchange", sa.text("captured_at DESC")],
        schema=OPS_SCHEMA_NAME,
    )
    op.create_table(
        OPERATOR_AUDIT_RECORDS_TABLE_NAME,
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("audit_id", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("scope_id", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.Text(), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column("source_ip_hash", sa.Text(), nullable=True),
        sa.Column("request_hash", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("requested_at", "audit_id", name="pk_operator_audit_records"),
        schema=AUDIT_SCHEMA_NAME,
        postgresql_partition_by="RANGE (requested_at)",
    )
    op.create_index(
        OPERATOR_AUDIT_ACTOR_TIME_INDEX_NAME,
        OPERATOR_AUDIT_RECORDS_TABLE_NAME,
        ["actor", sa.text("requested_at DESC")],
        schema=AUDIT_SCHEMA_NAME,
    )
    op.create_index(
        OPERATOR_AUDIT_SCOPE_TIME_INDEX_NAME,
        OPERATOR_AUDIT_RECORDS_TABLE_NAME,
        ["scope", "scope_id", sa.text("requested_at DESC")],
        schema=AUDIT_SCHEMA_NAME,
    )


def downgrade() -> None:
    """Drop adapter health and operator audit storage."""

    op.drop_index(
        OPERATOR_AUDIT_SCOPE_TIME_INDEX_NAME,
        table_name=OPERATOR_AUDIT_RECORDS_TABLE_NAME,
        schema=AUDIT_SCHEMA_NAME,
    )
    op.drop_index(
        OPERATOR_AUDIT_ACTOR_TIME_INDEX_NAME,
        table_name=OPERATOR_AUDIT_RECORDS_TABLE_NAME,
        schema=AUDIT_SCHEMA_NAME,
    )
    op.drop_table(OPERATOR_AUDIT_RECORDS_TABLE_NAME, schema=AUDIT_SCHEMA_NAME)
    op.drop_index(
        ADAPTER_HEALTH_EXCHANGE_TIME_INDEX_NAME,
        table_name=ADAPTER_HEALTH_SNAPSHOTS_TABLE_NAME,
        schema=OPS_SCHEMA_NAME,
    )
    op.drop_table(ADAPTER_HEALTH_SNAPSHOTS_TABLE_NAME, schema=OPS_SCHEMA_NAME)
