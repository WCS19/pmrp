"""SQLAlchemy row models for canonical market data storage."""

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
    desc,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pmrp.storage.models.base import StorageBase


class OrderBookSnapshotRow(StorageBase):
    """Current valid or invalid order-book projection row."""

    __tablename__ = "order_book_snapshots"
    __table_args__ = (
        Index("ix_order_book_snapshots__exchange_updated", "exchange", "updated_at"),
        {"schema": "pmrp_market"},
    )

    market_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("pmrp_market.markets.market_id"),
        primary_key=True,
    )
    contract_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("pmrp_market.contracts.contract_id"),
        primary_key=True,
    )
    exchange: Mapped[str] = mapped_column(Text, nullable=False)
    sequence: Mapped[int | None] = mapped_column(BigInteger)
    exchange_occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bids: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    asks: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    snapshot_reason: Mapped[str] = mapped_column(Text, nullable=False)
    aggregate_version: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("0"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class TradeRow(StorageBase):
    """Queryable canonical trade observation row."""

    __tablename__ = "trades"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity"),
        Index("ix_trades__market_time", "market_id", desc("exchange_occurred_at")),
        Index("ix_trades__contract_time", "contract_id", desc("exchange_occurred_at")),
        {
            "schema": "pmrp_market",
            "postgresql_partition_by": "RANGE (exchange_occurred_at)",
        },
    )

    exchange_occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
    )
    trade_id: Mapped[str] = mapped_column(Text, primary_key=True)
    exchange: Mapped[str] = mapped_column(Text, nullable=False)
    exchange_trade_id: Mapped[str] = mapped_column(Text, nullable=False)
    market_id: Mapped[str] = mapped_column(Text, nullable=False)
    contract_id: Mapped[str] = mapped_column(Text, nullable=False)
    outcome_id: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    aggressor_side: Mapped[str | None] = mapped_column(Text)
    liquidity_role: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sequence: Mapped[int | None] = mapped_column(BigInteger)
    source_event_id: Mapped[str] = mapped_column(Text, nullable=False)
