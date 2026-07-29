"""Create idempotency and dead-letter tables.

Revision ID: 0007_idempotency_dead_letters
Revises: 0006_processed_events_outbox
Create Date: 2026-07-29

Lock risk: low on empty databases; creates two unpartitioned tables and two
indexes across pmrp_core and pmrp_ops.
Expected runtime: under one second on empty local and CI PostgreSQL databases.
Rollback plan: downgrade drops dead_letter_records, then idempotency_records.
Backfill plan: not applicable; no rows are created or transformed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_idempotency_dead_letters"
down_revision: str | None = "0006_processed_events_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CORE_SCHEMA_NAME = "pmrp_core"
OPS_SCHEMA_NAME = "pmrp_ops"
IDEMPOTENCY_RECORDS_TABLE_NAME = "idempotency_records"
DEAD_LETTER_RECORDS_TABLE_NAME = "dead_letter_records"
IDEMPOTENCY_EXPIRES_INDEX_NAME = "ix_idempotency_records__expires"
DEAD_LETTER_UNRESOLVED_INDEX_NAME = "ix_dead_letter_records__unresolved"


def upgrade() -> None:
    """Create durable API idempotency and consumer failure storage."""

    op.create_table(
        IDEMPOTENCY_RECORDS_TABLE_NAME,
        sa.Column("subject_id", sa.Text(), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_headers", postgresql.JSONB(), nullable=True),
        sa.Column("response_body", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "subject_id",
            "operation",
            "idempotency_key",
            name="pk_idempotency_records",
        ),
        schema=CORE_SCHEMA_NAME,
    )
    op.create_index(
        IDEMPOTENCY_EXPIRES_INDEX_NAME,
        IDEMPOTENCY_RECORDS_TABLE_NAME,
        ["expires_at"],
        schema=CORE_SCHEMA_NAME,
    )
    op.create_table(
        DEAD_LETTER_RECORDS_TABLE_NAME,
        sa.Column("dead_letter_id", sa.Text(), nullable=False),
        sa.Column("source_event_id", sa.Text(), nullable=True),
        sa.Column("source_command_id", sa.Text(), nullable=True),
        sa.Column("consumer_name", sa.Text(), nullable=False),
        sa.Column("failure_category", sa.Text(), nullable=False),
        sa.Column("exception_type", sa.Text(), nullable=False),
        sa.Column("exception_message", sa.Text(), nullable=False),
        sa.Column("first_failed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_failed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("payload_reference", sa.Text(), nullable=False),
        sa.Column("replayable", sa.Boolean(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("dead_letter_id", name="pk_dead_letter_records"),
        schema=OPS_SCHEMA_NAME,
    )
    op.create_index(
        DEAD_LETTER_UNRESOLVED_INDEX_NAME,
        DEAD_LETTER_RECORDS_TABLE_NAME,
        ["last_failed_at"],
        schema=OPS_SCHEMA_NAME,
        postgresql_where=sa.text("resolved_at IS NULL"),
    )


def downgrade() -> None:
    """Drop durable API idempotency and consumer failure storage."""

    op.drop_index(
        DEAD_LETTER_UNRESOLVED_INDEX_NAME,
        table_name=DEAD_LETTER_RECORDS_TABLE_NAME,
        schema=OPS_SCHEMA_NAME,
    )
    op.drop_table(DEAD_LETTER_RECORDS_TABLE_NAME, schema=OPS_SCHEMA_NAME)
    op.drop_index(
        IDEMPOTENCY_EXPIRES_INDEX_NAME,
        table_name=IDEMPOTENCY_RECORDS_TABLE_NAME,
        schema=CORE_SCHEMA_NAME,
    )
    op.drop_table(IDEMPOTENCY_RECORDS_TABLE_NAME, schema=CORE_SCHEMA_NAME)
