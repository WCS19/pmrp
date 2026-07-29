"""Create canonical event and global event ID tables.

Revision ID: 0005_canonical_events
Revises: 0004_raw_exchange_records
Create Date: 2026-07-29

Lock risk: low on empty databases; creates one registry table, one partitioned
table, and four indexes in pmrp_event.
Expected runtime: under one second on empty local and CI PostgreSQL databases.
Rollback plan: downgrade drops canonical_events, then event_ids.
Backfill plan: not applicable; no rows are created or transformed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_canonical_events"
down_revision: str | None = "0004_raw_exchange_records"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_NAME = "pmrp_event"
EVENT_IDS_TABLE_NAME = "event_ids"
CANONICAL_EVENTS_TABLE_NAME = "canonical_events"
TYPE_TIME_INDEX_NAME = "ix_canonical_events__type_time"
MARKET_TIME_INDEX_NAME = "ix_canonical_events__market_time"
ORDER_TIME_INDEX_NAME = "ix_canonical_events__order_time"
CORRELATION_INDEX_NAME = "ix_canonical_events__correlation"
SCHEMA_VERSION_CHECK_NAME = "ck_canonical_events__schema_version"


def upgrade() -> None:
    """Create durable canonical event storage tables."""

    op.create_table(
        EVENT_IDS_TABLE_NAME,
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "inserted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("event_id", name="pk_event_ids"),
        schema=SCHEMA_NAME,
    )
    op.create_table(
        CANONICAL_EVENTS_TABLE_NAME,
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("producer", sa.Text(), nullable=False),
        sa.Column("exchange", sa.Text(), nullable=True),
        sa.Column("market_id", sa.Text(), nullable=True),
        sa.Column("account_id", sa.Text(), nullable=True),
        sa.Column("strategy_id", sa.Text(), nullable=True),
        sa.Column("order_id", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.Text(), nullable=False),
        sa.Column("causation_id", sa.Text(), nullable=True),
        sa.Column("trace_id", sa.Text(), nullable=True),
        sa.Column("replay_session_id", sa.Text(), nullable=True),
        sa.Column("simulation_session_id", sa.Text(), nullable=True),
        sa.Column(
            "quality_flags",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "attributes",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column(
            "inserted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("occurred_at", "event_id", name="pk_canonical_events"),
        sa.CheckConstraint(
            "schema_version >= 1",
            name=op.f(SCHEMA_VERSION_CHECK_NAME),
        ),
        schema=SCHEMA_NAME,
        postgresql_partition_by="RANGE (occurred_at)",
    )
    op.create_index(
        TYPE_TIME_INDEX_NAME,
        CANONICAL_EVENTS_TABLE_NAME,
        ["event_type", "occurred_at"],
        schema=SCHEMA_NAME,
    )
    op.create_index(
        MARKET_TIME_INDEX_NAME,
        CANONICAL_EVENTS_TABLE_NAME,
        ["market_id", "occurred_at"],
        schema=SCHEMA_NAME,
        postgresql_where=sa.text("market_id IS NOT NULL"),
    )
    op.create_index(
        ORDER_TIME_INDEX_NAME,
        CANONICAL_EVENTS_TABLE_NAME,
        ["order_id", "occurred_at"],
        schema=SCHEMA_NAME,
        postgresql_where=sa.text("order_id IS NOT NULL"),
    )
    op.create_index(
        CORRELATION_INDEX_NAME,
        CANONICAL_EVENTS_TABLE_NAME,
        ["correlation_id"],
        schema=SCHEMA_NAME,
    )


def downgrade() -> None:
    """Drop durable canonical event storage tables."""

    op.drop_index(
        CORRELATION_INDEX_NAME, table_name=CANONICAL_EVENTS_TABLE_NAME, schema=SCHEMA_NAME
    )
    op.drop_index(ORDER_TIME_INDEX_NAME, table_name=CANONICAL_EVENTS_TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_index(
        MARKET_TIME_INDEX_NAME, table_name=CANONICAL_EVENTS_TABLE_NAME, schema=SCHEMA_NAME
    )
    op.drop_index(TYPE_TIME_INDEX_NAME, table_name=CANONICAL_EVENTS_TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_table(CANONICAL_EVENTS_TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_table(EVENT_IDS_TABLE_NAME, schema=SCHEMA_NAME)
