"""Create processed event idempotency and outbox tables.

Revision ID: 0006_processed_events_outbox
Revises: 0005_canonical_events
Create Date: 2026-07-29

Lock risk: low on empty databases; creates two unpartitioned tables and two
indexes in pmrp_event.
Expected runtime: under one second on empty local and CI PostgreSQL databases.
Rollback plan: downgrade drops outbox_messages, then processed_events.
Backfill plan: not applicable; no rows are created or transformed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_processed_events_outbox"
down_revision: str | None = "0005_canonical_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_NAME = "pmrp_event"
PROCESSED_EVENTS_TABLE_NAME = "processed_events"
OUTBOX_MESSAGES_TABLE_NAME = "outbox_messages"
PROCESSED_EVENTS_TIME_INDEX_NAME = "ix_processed_events__time"
OUTBOX_PENDING_INDEX_NAME = "ix_outbox_messages__pending"
OUTBOX_EVENT_TOPIC_UNIQUE_NAME = "uq_outbox_messages__event_id_topic"


def upgrade() -> None:
    """Create processed event idempotency and outbox storage tables."""

    op.create_table(
        PROCESSED_EVENTS_TABLE_NAME,
        sa.Column("consumer_name", sa.Text(), nullable=False),
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("processing_version", sa.Text(), nullable=True),
        sa.Column("result_hash", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("consumer_name", "event_id", name="pk_processed_events"),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        PROCESSED_EVENTS_TIME_INDEX_NAME,
        PROCESSED_EVENTS_TABLE_NAME,
        ["processed_at"],
        schema=SCHEMA_NAME,
    )
    op.create_table(
        OUTBOX_MESSAGES_TABLE_NAME,
        sa.Column("outbox_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("partition_key", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "publish_attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("outbox_id", name="pk_outbox_messages"),
        sa.UniqueConstraint(
            "event_id",
            "topic",
            name=op.f(OUTBOX_EVENT_TOPIC_UNIQUE_NAME),
        ),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        OUTBOX_PENDING_INDEX_NAME,
        OUTBOX_MESSAGES_TABLE_NAME,
        ["available_at", "outbox_id"],
        schema=SCHEMA_NAME,
        postgresql_where=sa.text("published_at IS NULL"),
    )


def downgrade() -> None:
    """Drop processed event idempotency and outbox storage tables."""

    op.drop_index(
        OUTBOX_PENDING_INDEX_NAME, table_name=OUTBOX_MESSAGES_TABLE_NAME, schema=SCHEMA_NAME
    )
    op.drop_table(OUTBOX_MESSAGES_TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_index(
        PROCESSED_EVENTS_TIME_INDEX_NAME,
        table_name=PROCESSED_EVENTS_TABLE_NAME,
        schema=SCHEMA_NAME,
    )
    op.drop_table(PROCESSED_EVENTS_TABLE_NAME, schema=SCHEMA_NAME)
