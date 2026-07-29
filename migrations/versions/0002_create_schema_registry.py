"""Create schema registry table.

Revision ID: 0002_create_schema_registry
Revises: 0001_create_logical_schemas
Create Date: 2026-07-29

Lock risk: low on empty databases; creates one table and one index in pmrp_core.
Expected runtime: under one second on empty local and CI PostgreSQL databases.
Rollback plan: downgrade drops only pmrp_core.schema_registry.
Backfill plan: not applicable; no rows are created or transformed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_create_schema_registry"
down_revision: str | None = "0001_create_logical_schemas"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_NAME = "pmrp_core"
TABLE_NAME = "schema_registry"
CATEGORY_INDEX_NAME = "ix_schema_registry__category"


def upgrade() -> None:
    """Create the durable schema registry table."""

    op.create_table(
        TABLE_NAME,
        sa.Column("schema_name", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("schema_category", sa.Text(), nullable=False),
        sa.Column("python_model_path", sa.Text(), nullable=False),
        sa.Column("json_schema_uri", sa.Text(), nullable=True),
        sa.Column("introduced_in_platform_version", sa.Text(), nullable=False),
        sa.Column("deprecated_in_platform_version", sa.Text(), nullable=True),
        sa.Column(
            "backward_compatible_with",
            postgresql.ARRAY(sa.Integer()),
            nullable=False,
            server_default=sa.text("'{}'::integer[]"),
        ),
        sa.Column(
            "upcaster_paths",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("schema_name", "schema_version", name="pk_schema_registry"),
        sa.CheckConstraint("schema_version >= 1", name="ck_schema_registry__schema_version"),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        CATEGORY_INDEX_NAME,
        TABLE_NAME,
        ["schema_category"],
        schema=SCHEMA_NAME,
    )


def downgrade() -> None:
    """Drop the durable schema registry table."""

    op.drop_index(CATEGORY_INDEX_NAME, table_name=TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_table(TABLE_NAME, schema=SCHEMA_NAME)
