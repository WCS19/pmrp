"""Create strategy and model metadata tables.

Revision ID: 0010_strategy_model_metadata
Revises: 0009_order_books_trades
Create Date: 2026-07-29

Lock risk: low on empty databases; creates four unpartitioned tables and two
indexes in pmrp_research.
Expected runtime: under one second on empty local and CI PostgreSQL databases.
Rollback plan: downgrade drops model_artifacts, strategy_configurations,
strategy_instances, then strategy_definitions.
Backfill plan: not applicable; no rows are created or transformed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_strategy_model_metadata"
down_revision: str | None = "0009_order_books_trades"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_NAME = "pmrp_research"
STRATEGY_DEFINITIONS_TABLE_NAME = "strategy_definitions"
STRATEGY_INSTANCES_TABLE_NAME = "strategy_instances"
STRATEGY_CONFIGURATIONS_TABLE_NAME = "strategy_configurations"
MODEL_ARTIFACTS_TABLE_NAME = "model_artifacts"
STRATEGY_INSTANCES_STATE_HEALTH_INDEX_NAME = "ix_strategy_instances__state_health"
MODEL_ARTIFACTS_APPROVAL_INDEX_NAME = "ix_model_artifacts__approval"
STRATEGY_INSTANCES_DEFINITION_FOREIGN_KEY_NAME = (
    "fk_strategy_instances__strategy_type_strategy_version__strategy_definitions"
)
STRATEGY_CONFIGURATIONS_INSTANCE_FOREIGN_KEY_NAME = (
    "fk_strategy_configurations__strategy_id__strategy_instances"
)
STRATEGY_CONFIGURATIONS_HASH_UNIQUE_NAME = (
    "uq_strategy_configurations__strategy_id_configuration_hash"
)


def upgrade() -> None:
    """Create durable strategy and model metadata storage."""

    op.create_table(
        STRATEGY_DEFINITIONS_TABLE_NAME,
        sa.Column("strategy_type", sa.Text(), nullable=False),
        sa.Column("strategy_version", sa.Text(), nullable=False),
        sa.Column("implementation_path", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("configuration_schema_version", sa.Integer(), nullable=False),
        sa.Column("subscribed_event_types", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("supports_replay", sa.Boolean(), nullable=False),
        sa.Column("supports_simulation", sa.Boolean(), nullable=False),
        sa.Column("supports_paper", sa.Boolean(), nullable=False),
        sa.Column("supports_shadow", sa.Boolean(), nullable=False),
        sa.Column("supports_live", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint(
            "strategy_type",
            "strategy_version",
            name="pk_strategy_definitions",
        ),
        schema=SCHEMA_NAME,
    )
    op.create_table(
        STRATEGY_INSTANCES_TABLE_NAME,
        sa.Column("strategy_id", sa.Text(), nullable=False),
        sa.Column("strategy_type", sa.Text(), nullable=False),
        sa.Column("strategy_version", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("environment", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("configuration_version", sa.Integer(), nullable=False),
        sa.Column("configuration_hash", sa.Text(), nullable=False),
        sa.Column("capital_allocation_amount", sa.Numeric(38, 18), nullable=True),
        sa.Column("capital_allocation_currency", sa.Text(), nullable=True),
        sa.Column("health_status", sa.Text(), nullable=False),
        sa.Column("health_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "aggregate_version",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.PrimaryKeyConstraint("strategy_id", name="pk_strategy_instances"),
        sa.ForeignKeyConstraint(
            ["strategy_type", "strategy_version"],
            [
                f"{SCHEMA_NAME}.{STRATEGY_DEFINITIONS_TABLE_NAME}.strategy_type",
                f"{SCHEMA_NAME}.{STRATEGY_DEFINITIONS_TABLE_NAME}.strategy_version",
            ],
            name=op.f(STRATEGY_INSTANCES_DEFINITION_FOREIGN_KEY_NAME),
        ),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        STRATEGY_INSTANCES_STATE_HEALTH_INDEX_NAME,
        STRATEGY_INSTANCES_TABLE_NAME,
        ["state", "health_status"],
        schema=SCHEMA_NAME,
    )
    op.create_table(
        STRATEGY_CONFIGURATIONS_TABLE_NAME,
        sa.Column("strategy_id", sa.Text(), nullable=False),
        sa.Column("configuration_version", sa.Integer(), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("configuration", postgresql.JSONB(), nullable=False),
        sa.Column("configuration_hash", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("approved_by", sa.Text(), nullable=True),
        sa.Column(
            "approval_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint(
            "strategy_id",
            "configuration_version",
            name="pk_strategy_configurations",
        ),
        sa.ForeignKeyConstraint(
            ["strategy_id"],
            [f"{SCHEMA_NAME}.{STRATEGY_INSTANCES_TABLE_NAME}.strategy_id"],
            name=op.f(STRATEGY_CONFIGURATIONS_INSTANCE_FOREIGN_KEY_NAME),
        ),
        sa.UniqueConstraint(
            "strategy_id",
            "configuration_hash",
            name=op.f(STRATEGY_CONFIGURATIONS_HASH_UNIQUE_NAME),
        ),
        schema=SCHEMA_NAME,
    )
    op.create_table(
        MODEL_ARTIFACTS_TABLE_NAME,
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("model_version", sa.Text(), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("artifact_uri", sa.Text(), nullable=False),
        sa.Column("artifact_checksum", sa.Text(), nullable=False),
        sa.Column("training_dataset_id", sa.Text(), nullable=False),
        sa.Column("training_dataset_checksum", sa.Text(), nullable=False),
        sa.Column("training_code_commit", sa.Text(), nullable=False),
        sa.Column("dependency_lock_hash", sa.Text(), nullable=False),
        sa.Column("feature_schema_version", sa.Text(), nullable=False),
        sa.Column("target_definition", sa.Text(), nullable=False),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("random_seed", sa.BigInteger(), nullable=False),
        sa.Column("evaluation_metrics", postgresql.JSONB(), nullable=False),
        sa.Column("calibration_method", sa.Text(), nullable=True),
        sa.Column("approval_status", sa.Text(), nullable=False),
        sa.Column("approved_by", sa.Text(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("model_id", "model_version", name="pk_model_artifacts"),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        MODEL_ARTIFACTS_APPROVAL_INDEX_NAME,
        MODEL_ARTIFACTS_TABLE_NAME,
        ["approval_status", sa.text("trained_at DESC")],
        schema=SCHEMA_NAME,
    )


def downgrade() -> None:
    """Drop durable strategy and model metadata storage."""

    op.drop_index(
        MODEL_ARTIFACTS_APPROVAL_INDEX_NAME,
        table_name=MODEL_ARTIFACTS_TABLE_NAME,
        schema=SCHEMA_NAME,
    )
    op.drop_table(MODEL_ARTIFACTS_TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_table(STRATEGY_CONFIGURATIONS_TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_index(
        STRATEGY_INSTANCES_STATE_HEALTH_INDEX_NAME,
        table_name=STRATEGY_INSTANCES_TABLE_NAME,
        schema=SCHEMA_NAME,
    )
    op.drop_table(STRATEGY_INSTANCES_TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_table(STRATEGY_DEFINITIONS_TABLE_NAME, schema=SCHEMA_NAME)
