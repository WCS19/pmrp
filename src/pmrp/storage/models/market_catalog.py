"""SQLAlchemy row models for the canonical market catalog."""

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
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    desc,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pmrp.storage.models.base import StorageBase


class MarketRow(StorageBase):
    """Current canonical market catalog projection row."""

    __tablename__ = "markets"
    __table_args__ = (
        UniqueConstraint(
            "exchange",
            "exchange_market_id",
            name="uq_markets__exchange_exchange_market_id",
        ),
        CheckConstraint("payout_per_unit > 0", name="payout_per_unit"),
        CheckConstraint("tick_size > 0", name="tick_size"),
        CheckConstraint("quantity_increment > 0", name="quantity_increment"),
        Index("ix_markets__exchange_status", "exchange", "status"),
        Index("ix_markets__status_closes", "status", "closes_at"),
        Index("ix_markets__updated", desc("updated_at"), "market_id"),
        {"schema": "pmrp_market"},
    )

    market_id: Mapped[str] = mapped_column(Text, primary_key=True)
    exchange: Mapped[str] = mapped_column(Text, nullable=False)
    exchange_market_id: Mapped[str] = mapped_column(Text, nullable=False)
    exchange_event_id: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    subtitle: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{}'::text[]"),
    )
    outcome_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolves_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    payout_per_unit: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    tick_size: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    quantity_increment: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    rules_text: Mapped[str | None] = mapped_column(Text)
    rules_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    aggregate_version: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("0"),
    )


class OutcomeRow(StorageBase):
    """Canonical market outcome row."""

    __tablename__ = "outcomes"
    __table_args__ = (
        UniqueConstraint(
            "market_id",
            "outcome_index",
            name="uq_outcomes__market_id_outcome_index",
        ),
        UniqueConstraint(
            "market_id",
            "normalized_name",
            name="uq_outcomes__market_id_normalized_name",
        ),
        Index("ix_outcomes__market", "market_id", "outcome_index"),
        {"schema": "pmrp_market"},
    )

    outcome_id: Mapped[str] = mapped_column(Text, primary_key=True)
    market_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("pmrp_market.markets.market_id"),
        nullable=False,
    )
    exchange_outcome_id: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_name: Mapped[str] = mapped_column(Text, nullable=False)
    outcome_index: Mapped[int] = mapped_column(Integer, nullable=False)
    is_tradeable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
    is_winning: Mapped[bool | None] = mapped_column(Boolean)
    payout_per_unit: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    metadata_: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ContractRow(StorageBase):
    """Tradeable contract row associated with one market outcome."""

    __tablename__ = "contracts"
    __table_args__ = (
        UniqueConstraint("market_id", "outcome_id", name="uq_contracts__market_id_outcome_id"),
        Index("ix_contracts__market_active", "market_id", "active"),
        {"schema": "pmrp_market"},
    )

    contract_id: Mapped[str] = mapped_column(Text, primary_key=True)
    market_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("pmrp_market.markets.market_id"),
        nullable=False,
    )
    outcome_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("pmrp_market.outcomes.outcome_id"),
        nullable=False,
    )
    exchange_contract_id: Mapped[str | None] = mapped_column(Text)
    symbol: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    tick_size: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    quantity_increment: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    min_order_quantity: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    max_order_quantity: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
