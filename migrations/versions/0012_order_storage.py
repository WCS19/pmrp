"""Create order intent, order, and transition tables.

Revision ID: 0012_order_storage
Revises: 0011_signals_features
Create Date: 2026-07-29

Lock risk: low on empty databases; creates three unpartitioned tables and four
indexes in pmrp_execution.
Expected runtime: under one second on empty local and CI PostgreSQL databases.
Rollback plan: downgrade drops order_state_transitions, orders, then order_intents.
Backfill plan: not applicable; no rows are created or transformed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_order_storage"
down_revision: str | None = "0011_signals_features"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_NAME = "pmrp_execution"
ORDER_INTENTS_TABLE_NAME = "order_intents"
ORDERS_TABLE_NAME = "orders"
ORDER_STATE_TRANSITIONS_TABLE_NAME = "order_state_transitions"
ORDER_INTENTS_STRATEGY_TIME_INDEX_NAME = "ix_order_intents__strategy_time"
ORDERS_ACCOUNT_STATUS_INDEX_NAME = "ix_orders__account_status"
ORDERS_STRATEGY_CREATED_INDEX_NAME = "ix_orders__strategy_created"
ORDERS_ACTIVE_INDEX_NAME = "ix_orders__active"
ORDER_TRANSITIONS_ORDER_TIME_INDEX_NAME = "ix_order_transitions__order_time"
ORDER_INTENTS_IDEMPOTENCY_UNIQUE_NAME = "uq_order_intents__strategy_id_idempotency_key"
ORDERS_CLIENT_ORDER_UNIQUE_NAME = "uq_orders__exchange_account_client_order_id"
ORDERS_EXCHANGE_ORDER_UNIQUE_NAME = "uq_orders__exchange_account_exchange_order_id"
ORDER_TRANSITIONS_ORDER_VERSION_UNIQUE_NAME = "uq_order_transitions__order_version"
ORDER_TRANSITIONS_ORDER_FOREIGN_KEY_NAME = "fk_order_transitions__order_id__orders"
ORDER_INTENTS_QUANTITY_CHECK_NAME = "ck_order_intents__quantity"
ORDER_INTENTS_LIMIT_PRICE_CHECK_NAME = "ck_order_intents__limit_price"
ORDERS_QUANTITY_CHECK_NAME = "ck_orders__quantity"
ORDERS_FILLED_QUANTITY_CHECK_NAME = "ck_orders__filled_quantity"
ORDERS_REMAINING_QUANTITY_CHECK_NAME = "ck_orders__remaining_quantity"
ORDERS_FILL_BALANCE_CHECK_NAME = "ck_orders__fill_balance"


def upgrade() -> None:
    """Create canonical order intent, order, and transition storage."""

    op.create_table(
        ORDER_INTENTS_TABLE_NAME,
        sa.Column("intent_id", sa.Text(), nullable=False),
        sa.Column("strategy_id", sa.Text(), nullable=False),
        sa.Column("market_id", sa.Text(), nullable=False),
        sa.Column("contract_id", sa.Text(), nullable=False),
        sa.Column("outcome_id", sa.Text(), nullable=False),
        sa.Column("side", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Numeric(38, 18), nullable=False),
        sa.Column("limit_price", sa.Numeric(38, 18), nullable=True),
        sa.Column("order_type", sa.Text(), nullable=False),
        sa.Column("time_in_force", sa.Text(), nullable=False),
        sa.Column("post_only", sa.Boolean(), nullable=False),
        sa.Column("reduce_only", sa.Boolean(), nullable=False),
        sa.Column("urgency", sa.Numeric(38, 18), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "signal_ids",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("correlation_id", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("intent_id", name="pk_order_intents"),
        sa.UniqueConstraint(
            "strategy_id",
            "idempotency_key",
            name=op.f(ORDER_INTENTS_IDEMPOTENCY_UNIQUE_NAME),
        ),
        sa.CheckConstraint("quantity > 0", name=op.f(ORDER_INTENTS_QUANTITY_CHECK_NAME)),
        sa.CheckConstraint(
            "(order_type = 'limit' AND limit_price IS NOT NULL) OR order_type <> 'limit'",
            name=op.f(ORDER_INTENTS_LIMIT_PRICE_CHECK_NAME),
        ),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        ORDER_INTENTS_STRATEGY_TIME_INDEX_NAME,
        ORDER_INTENTS_TABLE_NAME,
        ["strategy_id", sa.text("created_at DESC")],
        schema=SCHEMA_NAME,
    )
    op.create_table(
        ORDERS_TABLE_NAME,
        sa.Column("order_id", sa.Text(), nullable=False),
        sa.Column("intent_id", sa.Text(), nullable=True),
        sa.Column("strategy_id", sa.Text(), nullable=True),
        sa.Column("risk_decision_id", sa.Text(), nullable=True),
        sa.Column("exchange", sa.Text(), nullable=False),
        sa.Column("account_id", sa.Text(), nullable=False),
        sa.Column("market_id", sa.Text(), nullable=False),
        sa.Column("contract_id", sa.Text(), nullable=False),
        sa.Column("outcome_id", sa.Text(), nullable=False),
        sa.Column("side", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Numeric(38, 18), nullable=False),
        sa.Column(
            "filled_quantity",
            sa.Numeric(38, 18),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("remaining_quantity", sa.Numeric(38, 18), nullable=False),
        sa.Column("limit_price", sa.Numeric(38, 18), nullable=True),
        sa.Column("average_fill_price", sa.Numeric(38, 18), nullable=True),
        sa.Column("order_type", sa.Text(), nullable=False),
        sa.Column("time_in_force", sa.Text(), nullable=False),
        sa.Column("post_only", sa.Boolean(), nullable=False),
        sa.Column("reduce_only", sa.Boolean(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("client_order_id", sa.Text(), nullable=False),
        sa.Column("exchange_order_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "aggregate_version",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.PrimaryKeyConstraint("order_id", name="pk_orders"),
        sa.UniqueConstraint(
            "exchange",
            "account_id",
            "client_order_id",
            name=op.f(ORDERS_CLIENT_ORDER_UNIQUE_NAME),
        ),
        sa.UniqueConstraint(
            "exchange",
            "account_id",
            "exchange_order_id",
            name=op.f(ORDERS_EXCHANGE_ORDER_UNIQUE_NAME),
        ),
        sa.CheckConstraint("quantity > 0", name=op.f(ORDERS_QUANTITY_CHECK_NAME)),
        sa.CheckConstraint(
            "filled_quantity >= 0",
            name=op.f(ORDERS_FILLED_QUANTITY_CHECK_NAME),
        ),
        sa.CheckConstraint(
            "remaining_quantity >= 0",
            name=op.f(ORDERS_REMAINING_QUANTITY_CHECK_NAME),
        ),
        sa.CheckConstraint(
            "filled_quantity + remaining_quantity = quantity",
            name=op.f(ORDERS_FILL_BALANCE_CHECK_NAME),
        ),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        ORDERS_ACCOUNT_STATUS_INDEX_NAME,
        ORDERS_TABLE_NAME,
        ["exchange", "account_id", "status"],
        schema=SCHEMA_NAME,
    )
    op.create_index(
        ORDERS_STRATEGY_CREATED_INDEX_NAME,
        ORDERS_TABLE_NAME,
        ["strategy_id", sa.text("created_at DESC")],
        schema=SCHEMA_NAME,
        postgresql_where=sa.text("strategy_id IS NOT NULL"),
    )
    op.create_index(
        ORDERS_ACTIVE_INDEX_NAME,
        ORDERS_TABLE_NAME,
        ["exchange", "account_id", "created_at"],
        schema=SCHEMA_NAME,
        postgresql_where=sa.text(
            "status IN ('submitted','accepted','partially_filled','cancel_requested','cancelling')"
        ),
    )
    op.create_table(
        ORDER_STATE_TRANSITIONS_TABLE_NAME,
        sa.Column("transition_id", sa.Text(), nullable=False),
        sa.Column("order_id", sa.Text(), nullable=False),
        sa.Column("previous_status", sa.Text(), nullable=True),
        sa.Column("current_status", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_event_id", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=True),
        sa.Column("reason_text", sa.Text(), nullable=True),
        sa.Column("aggregate_version_before", sa.BigInteger(), nullable=False),
        sa.Column("aggregate_version_after", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("transition_id", name="pk_order_state_transitions"),
        sa.ForeignKeyConstraint(
            ["order_id"],
            [f"{SCHEMA_NAME}.{ORDERS_TABLE_NAME}.order_id"],
            name=op.f(ORDER_TRANSITIONS_ORDER_FOREIGN_KEY_NAME),
        ),
        sa.UniqueConstraint(
            "order_id",
            "aggregate_version_after",
            name=op.f(ORDER_TRANSITIONS_ORDER_VERSION_UNIQUE_NAME),
        ),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        ORDER_TRANSITIONS_ORDER_TIME_INDEX_NAME,
        ORDER_STATE_TRANSITIONS_TABLE_NAME,
        ["order_id", "occurred_at"],
        schema=SCHEMA_NAME,
    )


def downgrade() -> None:
    """Drop canonical order intent, order, and transition storage."""

    op.drop_index(
        ORDER_TRANSITIONS_ORDER_TIME_INDEX_NAME,
        table_name=ORDER_STATE_TRANSITIONS_TABLE_NAME,
        schema=SCHEMA_NAME,
    )
    op.drop_table(ORDER_STATE_TRANSITIONS_TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_index(ORDERS_ACTIVE_INDEX_NAME, table_name=ORDERS_TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_index(
        ORDERS_STRATEGY_CREATED_INDEX_NAME,
        table_name=ORDERS_TABLE_NAME,
        schema=SCHEMA_NAME,
    )
    op.drop_index(
        ORDERS_ACCOUNT_STATUS_INDEX_NAME,
        table_name=ORDERS_TABLE_NAME,
        schema=SCHEMA_NAME,
    )
    op.drop_table(ORDERS_TABLE_NAME, schema=SCHEMA_NAME)
    op.drop_index(
        ORDER_INTENTS_STRATEGY_TIME_INDEX_NAME,
        table_name=ORDER_INTENTS_TABLE_NAME,
        schema=SCHEMA_NAME,
    )
    op.drop_table(ORDER_INTENTS_TABLE_NAME, schema=SCHEMA_NAME)
