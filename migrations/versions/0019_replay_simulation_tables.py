"""Create replay and simulation tables.

Revision ID: 0019_replay_simulation_tables
Revises: 0018_reconciliation_tables
Create Date: 2026-08-01

Lock risk: low on empty databases; creates three unpartitioned tables and two
indexes in pmrp_research.
Expected runtime: under one second on empty local and CI PostgreSQL databases.
Rollback plan: downgrade drops simulation_sessions, replay_results, then
replay_sessions.
Backfill plan: not applicable; no rows are created or transformed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_replay_simulation_tables"
down_revision: str | None = "0018_reconciliation_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_NAME = "pmrp_research"
REPLAY_SESSIONS_TABLE_NAME = "replay_sessions"
REPLAY_RESULTS_TABLE_NAME = "replay_results"
SIMULATION_SESSIONS_TABLE_NAME = "simulation_sessions"
REPLAY_SESSIONS_STATE_CREATED_INDEX_NAME = "ix_replay_sessions__state_created"
SIMULATION_SESSIONS_STATE_CREATED_INDEX_NAME = "ix_simulation_sessions__state_created"
REPLAY_RESULTS_SESSION_FOREIGN_KEY_NAME = "fk_replay_results__replay_sessions"
SIMULATION_SESSIONS_REPLAY_FOREIGN_KEY_NAME = "fk_simulation_sessions__replay_sessions"


def upgrade() -> None:
    """Create deterministic replay and simulation lifecycle storage."""

    op.create_table(
        REPLAY_SESSIONS_TABLE_NAME,
        sa.Column("replay_session_id", sa.Text(), nullable=False),
        sa.Column("dataset_id", sa.Text(), nullable=False),
        sa.Column("dataset_checksum", sa.Text(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("speed", sa.Numeric(38, 18), nullable=False),
        sa.Column("deterministic", sa.Boolean(), nullable=False),
        sa.Column("random_seed", sa.BigInteger(), nullable=False),
        sa.Column("event_ordering_policy_version", sa.Text(), nullable=False),
        sa.Column("strategy_versions", postgresql.JSONB(), nullable=False),
        sa.Column("model_versions", postgresql.JSONB(), nullable=False),
        sa.Column("configuration_hash", sa.Text(), nullable=False),
        sa.Column("code_commit", sa.Text(), nullable=False),
        sa.Column("dependency_lock_hash", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("current_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "processed_events",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "rejected_events",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_checksum", sa.Text(), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("replay_session_id", name="pk_replay_sessions"),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        REPLAY_SESSIONS_STATE_CREATED_INDEX_NAME,
        REPLAY_SESSIONS_TABLE_NAME,
        ["state", sa.text("created_at DESC")],
        schema=SCHEMA_NAME,
    )
    op.create_table(
        REPLAY_RESULTS_TABLE_NAME,
        sa.Column("replay_session_id", sa.Text(), nullable=False),
        sa.Column("processed_events", sa.BigInteger(), nullable=False),
        sa.Column("generated_signals", sa.BigInteger(), nullable=False),
        sa.Column("generated_intents", sa.BigInteger(), nullable=False),
        sa.Column("simulated_orders", sa.BigInteger(), nullable=False),
        sa.Column("simulated_fills", sa.BigInteger(), nullable=False),
        sa.Column("final_portfolio", postgresql.JSONB(), nullable=False),
        sa.Column("metrics", postgresql.JSONB(), nullable=False),
        sa.Column("result_checksum", sa.Text(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("replay_session_id", name="pk_replay_results"),
        sa.ForeignKeyConstraint(
            ["replay_session_id"],
            [f"{SCHEMA_NAME}.{REPLAY_SESSIONS_TABLE_NAME}.replay_session_id"],
            name=op.f(REPLAY_RESULTS_SESSION_FOREIGN_KEY_NAME),
        ),
        schema=SCHEMA_NAME,
    )
    op.create_table(
        SIMULATION_SESSIONS_TABLE_NAME,
        sa.Column("simulation_session_id", sa.Text(), nullable=False),
        sa.Column("replay_session_id", sa.Text(), nullable=True),
        sa.Column("configuration", postgresql.JSONB(), nullable=False),
        sa.Column("configuration_hash", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_checksum", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("simulation_session_id", name="pk_simulation_sessions"),
        sa.ForeignKeyConstraint(
            ["replay_session_id"],
            [f"{SCHEMA_NAME}.{REPLAY_SESSIONS_TABLE_NAME}.replay_session_id"],
            name=op.f(SIMULATION_SESSIONS_REPLAY_FOREIGN_KEY_NAME),
        ),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        SIMULATION_SESSIONS_STATE_CREATED_INDEX_NAME,
        SIMULATION_SESSIONS_TABLE_NAME,
        ["state", sa.text("created_at DESC")],
        schema=SCHEMA_NAME,
    )


def downgrade() -> None:
    """Drop deterministic replay and simulation lifecycle storage."""

    op.drop_index(
        SIMULATION_SESSIONS_STATE_CREATED_INDEX_NAME,
        table_name=SIMULATION_SESSIONS_TABLE_NAME,
        schema=SCHEMA_NAME,
    )
    op.drop_table(SIMULATION_SESSIONS_TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_table(REPLAY_RESULTS_TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_index(
        REPLAY_SESSIONS_STATE_CREATED_INDEX_NAME,
        table_name=REPLAY_SESSIONS_TABLE_NAME,
        schema=SCHEMA_NAME,
    )
    op.drop_table(REPLAY_SESSIONS_TABLE_NAME, schema=SCHEMA_NAME)
