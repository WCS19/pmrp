"""Create logical database schemas.

Revision ID: 0001_create_logical_schemas
Revises:
Create Date: 2026-07-29

Lock risk: low on empty databases; CREATE SCHEMA and CREATE EXTENSION acquire
catalog locks only.
Expected runtime: under one second on empty local and CI PostgreSQL databases.
Rollback plan: downgrade drops only empty PMRP schemas after later migrations
have been downgraded; pgcrypto is left installed because it may be shared.
Backfill plan: not applicable; no data is created or transformed.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy.schema import CreateSchema, DropSchema

revision: str = "0001_create_logical_schemas"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LOGICAL_SCHEMAS: tuple[str, ...] = (
    "pmrp_core",
    "pmrp_raw",
    "pmrp_event",
    "pmrp_market",
    "pmrp_execution",
    "pmrp_portfolio",
    "pmrp_risk",
    "pmrp_research",
    "pmrp_ops",
    "pmrp_audit",
)


def upgrade() -> None:
    """Create PMRP logical schemas and required PostgreSQL extension."""

    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    for schema_name in LOGICAL_SCHEMAS:
        op.execute(CreateSchema(schema_name, if_not_exists=True))


def downgrade() -> None:
    """Drop PMRP logical schemas after dependent objects are removed."""

    for schema_name in reversed(LOGICAL_SCHEMAS):
        op.execute(DropSchema(schema_name, if_exists=True))
