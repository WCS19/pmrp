"""Create market relationship matching table.

Revision ID: 0020_market_relationships
Revises: 0019_replay_simulation_tables
Create Date: 2026-08-01

Lock risk: low on empty databases; creates one unpartitioned table and one
index in pmrp_research.
Expected runtime: under one second on empty local and CI PostgreSQL databases.
Rollback plan: downgrade drops market_relationships.
Backfill plan: not applicable; no rows are created or transformed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020_market_relationships"
down_revision: str | None = "0019_replay_simulation_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_NAME = "pmrp_research"
MARKET_RELATIONSHIPS_TABLE_NAME = "market_relationships"
MARKET_RELATIONSHIPS_SOURCE_TARGET_INDEX_NAME = "ix_market_relationships__source_target"
MARKET_RELATIONSHIPS_SOURCE_TARGET_TYPE_UNIQUE_NAME = "uq_market_relationships__source_target_type"
MARKET_RELATIONSHIPS_CONFIDENCE_CHECK_NAME = "ck_market_relationships__confidence"


def upgrade() -> None:
    """Create approved and reviewed market relationship storage."""

    op.create_table(
        MARKET_RELATIONSHIPS_TABLE_NAME,
        sa.Column("relationship_id", sa.Text(), nullable=False),
        sa.Column("source_market_id", sa.Text(), nullable=False),
        sa.Column("target_market_id", sa.Text(), nullable=False),
        sa.Column("relationship_type", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(38, 18), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("validator_version", sa.Text(), nullable=False),
        sa.Column("settlement_rule_match", sa.Boolean(), nullable=True),
        sa.Column("human_review_status", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "aggregate_version",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.PrimaryKeyConstraint("relationship_id", name="pk_market_relationships"),
        sa.UniqueConstraint(
            "source_market_id",
            "target_market_id",
            "relationship_type",
            name=op.f(MARKET_RELATIONSHIPS_SOURCE_TARGET_TYPE_UNIQUE_NAME),
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name=op.f(MARKET_RELATIONSHIPS_CONFIDENCE_CHECK_NAME),
        ),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        MARKET_RELATIONSHIPS_SOURCE_TARGET_INDEX_NAME,
        MARKET_RELATIONSHIPS_TABLE_NAME,
        ["source_market_id", "target_market_id"],
        schema=SCHEMA_NAME,
    )


def downgrade() -> None:
    """Drop approved and reviewed market relationship storage."""

    op.drop_index(
        MARKET_RELATIONSHIPS_SOURCE_TARGET_INDEX_NAME,
        table_name=MARKET_RELATIONSHIPS_TABLE_NAME,
        schema=SCHEMA_NAME,
    )
    op.drop_table(MARKET_RELATIONSHIPS_TABLE_NAME, schema=SCHEMA_NAME)
