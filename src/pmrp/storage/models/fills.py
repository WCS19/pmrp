"""SQLAlchemy row models for canonical fill execution storage."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, Index, Numeric, Text, UniqueConstraint, desc, text
from sqlalchemy.orm import Mapped, mapped_column

from pmrp.storage.models.base import StorageBase


class FillRow(StorageBase):
    """Append-only exchange fill applied to an order and portfolio."""

    __tablename__ = "fills"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity"),
        Index("ix_fills__order_time", "order_id", "exchange_occurred_at"),
        Index("ix_fills__account_time", "exchange", "account_id", desc("exchange_occurred_at")),
        {
            "schema": "pmrp_execution",
            "postgresql_partition_by": "RANGE (exchange_occurred_at)",
        },
    )

    exchange_occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
    )
    fill_id: Mapped[str] = mapped_column(Text, primary_key=True)
    exchange_fill_id: Mapped[str] = mapped_column(Text, nullable=False)
    order_id: Mapped[str] = mapped_column(Text, nullable=False)
    exchange_order_id: Mapped[str | None] = mapped_column(Text)
    client_order_id: Mapped[str] = mapped_column(Text, nullable=False)
    exchange: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[str] = mapped_column(Text, nullable=False)
    market_id: Mapped[str] = mapped_column(Text, nullable=False)
    contract_id: Mapped[str] = mapped_column(Text, nullable=False)
    outcome_id: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    liquidity_role: Mapped[str] = mapped_column(Text, nullable=False)
    fee_amount: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    fee_currency: Mapped[str | None] = mapped_column(Text)
    rebate_amount: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    rebate_currency: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    trade_id: Mapped[str | None] = mapped_column(Text)
    source_event_id: Mapped[str] = mapped_column(Text, nullable=False)


class FillIdRow(StorageBase):
    """Global fill idempotency registry row."""

    __tablename__ = "fill_ids"
    __table_args__ = (
        UniqueConstraint("fill_id", name="uq_fill_ids__fill_id"),
        {"schema": "pmrp_execution"},
    )

    exchange: Mapped[str] = mapped_column(Text, primary_key=True)
    account_id: Mapped[str] = mapped_column(Text, primary_key=True)
    exchange_fill_id: Mapped[str] = mapped_column(Text, primary_key=True)
    fill_id: Mapped[str] = mapped_column(Text, nullable=False)
    exchange_occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
