"""Create raw exchange record table.

Revision ID: 0004_raw_exchange_records
Revises: 0003_exchange_account_registries
Create Date: 2026-07-29

Lock risk: low on empty databases; creates one partitioned table and indexes.
Expected runtime: under one second on empty local and CI PostgreSQL databases.
Rollback plan: downgrade drops indexes, then pmrp_raw.exchange_records.
Backfill plan: not applicable; no rows are created or transformed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_raw_exchange_records"
down_revision: str | None = "0003_exchange_account_registries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_NAME = "pmrp_raw"
TABLE_NAME = "exchange_records"
EXCHANGE_RECEIVED_INDEX_NAME = "ix_exchange_records__exchange_received"
CHANNEL_RECEIVED_INDEX_NAME = "ix_exchange_records__channel_received"
PAYLOAD_HASH_INDEX_NAME = "ix_exchange_records__payload_hash"
PAYLOAD_STORAGE_CHECK_NAME = "ck_exchange_records__payload_storage"


def upgrade() -> None:
    """Create the durable raw exchange record table."""

    op.create_table(
        TABLE_NAME,
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_record_id", sa.Text(), nullable=False),
        sa.Column("exchange", sa.Text(), nullable=False),
        sa.Column("environment", sa.Text(), nullable=False),
        sa.Column("connection_id", sa.Text(), nullable=True),
        sa.Column("endpoint", sa.Text(), nullable=True),
        sa.Column("channel", sa.Text(), nullable=True),
        sa.Column("message_type", sa.Text(), nullable=True),
        sa.Column("exchange_occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sequence", sa.BigInteger(), nullable=True),
        sa.Column(
            "content_type",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'application/json'"),
        ),
        sa.Column("compression", sa.Text(), nullable=True),
        sa.Column("payload_text", sa.Text(), nullable=True),
        sa.Column("payload_bytes", sa.LargeBinary(), nullable=True),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column("parser_version", sa.Text(), nullable=True),
        sa.Column(
            "transport_metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "inserted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("received_at", "raw_record_id", name="pk_exchange_records"),
        sa.CheckConstraint(
            """
            (
                payload_text IS NOT NULL
                AND payload_bytes IS NULL
            )
            OR (
                payload_text IS NULL
                AND payload_bytes IS NOT NULL
            )
            """,
            name=op.f(PAYLOAD_STORAGE_CHECK_NAME),
        ),
        schema=SCHEMA_NAME,
        postgresql_partition_by="RANGE (received_at)",
    )
    op.create_index(
        EXCHANGE_RECEIVED_INDEX_NAME,
        TABLE_NAME,
        ["exchange", "received_at"],
        schema=SCHEMA_NAME,
    )
    op.create_index(
        CHANNEL_RECEIVED_INDEX_NAME,
        TABLE_NAME,
        ["channel", "received_at"],
        schema=SCHEMA_NAME,
    )
    op.create_index(
        PAYLOAD_HASH_INDEX_NAME,
        TABLE_NAME,
        ["payload_hash"],
        schema=SCHEMA_NAME,
    )


def downgrade() -> None:
    """Drop the durable raw exchange record table."""

    op.drop_index(PAYLOAD_HASH_INDEX_NAME, table_name=TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_index(CHANNEL_RECEIVED_INDEX_NAME, table_name=TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_index(EXCHANGE_RECEIVED_INDEX_NAME, table_name=TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_table(TABLE_NAME, schema=SCHEMA_NAME)
