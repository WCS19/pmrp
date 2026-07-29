"""Create exchange and account registry tables.

Revision ID: 0003_exchange_account_registries
Revises: 0002_create_schema_registry
Create Date: 2026-07-29

Lock risk: low on empty databases; creates two tables and one index in pmrp_core.
Expected runtime: under one second on empty local and CI PostgreSQL databases.
Rollback plan: downgrade drops exchange_accounts, then exchanges.
Backfill plan: not applicable; no rows are created or transformed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_exchange_account_registries"
down_revision: str | None = "0002_create_schema_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_NAME = "pmrp_core"
EXCHANGES_TABLE_NAME = "exchanges"
EXCHANGE_ACCOUNTS_TABLE_NAME = "exchange_accounts"
EXCHANGE_ACCOUNT_INDEX_NAME = "ix_exchange_accounts__exchange_environment"
EXCHANGE_ACCOUNT_FOREIGN_KEY_NAME = "fk_exchange_accounts__exchange__exchanges"


def upgrade() -> None:
    """Create the durable exchange registry tables."""

    op.create_table(
        EXCHANGES_TABLE_NAME,
        sa.Column("exchange", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "capabilities",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("exchange", name="pk_exchanges"),
        schema=SCHEMA_NAME,
    )
    op.create_table(
        EXCHANGE_ACCOUNTS_TABLE_NAME,
        sa.Column("account_id", sa.Text(), nullable=False),
        sa.Column("exchange", sa.Text(), nullable=False),
        sa.Column("environment", sa.Text(), nullable=False),
        sa.Column("external_account_id", sa.Text(), nullable=True),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("account_id", name="pk_exchange_accounts"),
        sa.ForeignKeyConstraint(
            ["exchange"],
            [f"{SCHEMA_NAME}.{EXCHANGES_TABLE_NAME}.exchange"],
            name=op.f(EXCHANGE_ACCOUNT_FOREIGN_KEY_NAME),
        ),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        EXCHANGE_ACCOUNT_INDEX_NAME,
        EXCHANGE_ACCOUNTS_TABLE_NAME,
        ["exchange", "environment"],
        schema=SCHEMA_NAME,
    )


def downgrade() -> None:
    """Drop the durable exchange registry tables."""

    op.drop_index(
        EXCHANGE_ACCOUNT_INDEX_NAME,
        table_name=EXCHANGE_ACCOUNTS_TABLE_NAME,
        schema=SCHEMA_NAME,
    )
    op.drop_table(EXCHANGE_ACCOUNTS_TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_table(EXCHANGES_TABLE_NAME, schema=SCHEMA_NAME)
