"""SQLAlchemy row models for canonical order execution storage."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    desc,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from pmrp.storage.models.base import StorageBase


class OrderIntentRow(StorageBase):
    """Immutable strategy request before risk approval."""

    __tablename__ = "order_intents"
    __table_args__ = (
        UniqueConstraint(
            "strategy_id",
            "idempotency_key",
            name="uq_order_intents__strategy_id_idempotency_key",
        ),
        CheckConstraint("quantity > 0", name="quantity"),
        CheckConstraint(
            "(order_type = 'limit' AND limit_price IS NOT NULL) OR order_type <> 'limit'",
            name="limit_price",
        ),
        Index("ix_order_intents__strategy_time", "strategy_id", desc("created_at")),
        {"schema": "pmrp_execution"},
    )

    intent_id: Mapped[str] = mapped_column(Text, primary_key=True)
    strategy_id: Mapped[str] = mapped_column(Text, nullable=False)
    market_id: Mapped[str] = mapped_column(Text, nullable=False)
    contract_id: Mapped[str] = mapped_column(Text, nullable=False)
    outcome_id: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    order_type: Mapped[str] = mapped_column(Text, nullable=False)
    time_in_force: Mapped[str] = mapped_column(Text, nullable=False)
    post_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reduce_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    urgency: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    signal_ids: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{}'::text[]"),
    )
    correlation_id: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)


class OrderRow(StorageBase):
    """Current canonical order aggregate row."""

    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint(
            "exchange",
            "account_id",
            "client_order_id",
            name="uq_orders__exchange_account_client_order_id",
        ),
        UniqueConstraint(
            "exchange",
            "account_id",
            "exchange_order_id",
            name="uq_orders__exchange_account_exchange_order_id",
        ),
        CheckConstraint("quantity > 0", name="quantity"),
        CheckConstraint("filled_quantity >= 0", name="filled_quantity"),
        CheckConstraint("remaining_quantity >= 0", name="remaining_quantity"),
        CheckConstraint("filled_quantity + remaining_quantity = quantity", name="fill_balance"),
        Index("ix_orders__account_status", "exchange", "account_id", "status"),
        Index(
            "ix_orders__strategy_created",
            "strategy_id",
            desc("created_at"),
            postgresql_where=text("strategy_id IS NOT NULL"),
        ),
        Index(
            "ix_orders__active",
            "exchange",
            "account_id",
            "created_at",
            postgresql_where=text(
                "status IN "
                "('submitted','accepted','partially_filled','cancel_requested','cancelling')"
            ),
        ),
        {"schema": "pmrp_execution"},
    )

    order_id: Mapped[str] = mapped_column(Text, primary_key=True)
    intent_id: Mapped[str | None] = mapped_column(Text)
    strategy_id: Mapped[str | None] = mapped_column(Text)
    risk_decision_id: Mapped[str | None] = mapped_column(Text)
    exchange: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[str] = mapped_column(Text, nullable=False)
    market_id: Mapped[str] = mapped_column(Text, nullable=False)
    contract_id: Mapped[str] = mapped_column(Text, nullable=False)
    outcome_id: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    filled_quantity: Mapped[Decimal] = mapped_column(
        Numeric(38, 18),
        nullable=False,
        server_default=text("0"),
    )
    remaining_quantity: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    average_fill_price: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    order_type: Mapped[str] = mapped_column(Text, nullable=False)
    time_in_force: Mapped[str] = mapped_column(Text, nullable=False)
    post_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reduce_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    client_order_id: Mapped[str] = mapped_column(Text, nullable=False)
    exchange_order_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    aggregate_version: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("0"),
    )


class OrderStateTransitionRow(StorageBase):
    """Append-only validated order lifecycle transition row."""

    __tablename__ = "order_state_transitions"
    __table_args__ = (
        UniqueConstraint(
            "order_id",
            "aggregate_version_after",
            name="uq_order_transitions__order_version",
        ),
        Index("ix_order_transitions__order_time", "order_id", "occurred_at"),
        {"schema": "pmrp_execution"},
    )

    transition_id: Mapped[str] = mapped_column(Text, primary_key=True)
    order_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "pmrp_execution.orders.order_id",
            name="fk_order_transitions__order_id__orders",
        ),
        nullable=False,
    )
    previous_status: Mapped[str | None] = mapped_column(Text)
    current_status: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_event_id: Mapped[str] = mapped_column(Text, nullable=False)
    reason_code: Mapped[str | None] = mapped_column(Text)
    reason_text: Mapped[str | None] = mapped_column(Text)
    aggregate_version_before: Mapped[int] = mapped_column(BigInteger, nullable=False)
    aggregate_version_after: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
