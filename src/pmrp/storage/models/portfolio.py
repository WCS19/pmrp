"""SQLAlchemy row models for portfolio projection and journal storage."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pmrp.storage.models.base import StorageBase


class PositionRow(StorageBase):
    """Current exact position projection per account and contract."""

    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint(
            "exchange",
            "account_id",
            "contract_id",
            name="uq_positions__exchange_account_contract",
        ),
        Index("ix_positions__account_market", "exchange", "account_id", "market_id"),
        {"schema": "pmrp_portfolio"},
    )

    position_id: Mapped[str] = mapped_column(Text, primary_key=True)
    exchange: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[str] = mapped_column(Text, nullable=False)
    market_id: Mapped[str] = mapped_column(Text, nullable=False)
    contract_id: Mapped[str] = mapped_column(Text, nullable=False)
    outcome_id: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    average_entry_price: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    realized_pnl_amount: Mapped[Decimal] = mapped_column(
        Numeric(38, 18),
        nullable=False,
        server_default=text("0"),
    )
    unrealized_pnl_amount: Mapped[Decimal] = mapped_column(
        Numeric(38, 18),
        nullable=False,
        server_default=text("0"),
    )
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    fees_paid_amount: Mapped[Decimal] = mapped_column(
        Numeric(38, 18),
        nullable=False,
        server_default=text("0"),
    )
    rebates_received_amount: Mapped[Decimal] = mapped_column(
        Numeric(38, 18),
        nullable=False,
        server_default=text("0"),
    )
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    aggregate_version: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("0"),
    )


class CashBalanceRow(StorageBase):
    """Current available, reserved, and total cash balance projection."""

    __tablename__ = "cash_balances"
    __table_args__ = (
        UniqueConstraint(
            "exchange",
            "account_id",
            "currency",
            name="uq_cash_balances__exchange_account_currency",
        ),
        CheckConstraint("available + reserved = total", name="balance_identity"),
        {"schema": "pmrp_portfolio"},
    )

    balance_id: Mapped[str] = mapped_column(Text, primary_key=True)
    exchange: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[str] = mapped_column(Text, nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    available: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    reserved: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    aggregate_version: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("0"),
    )


class JournalEntryRow(StorageBase):
    """Append-only accounting journal header."""

    __tablename__ = "journal_entries"
    __table_args__ = (
        UniqueConstraint("source_event_id", name="uq_journal_entries__source_event_id"),
        Index("ix_journal_entries__reference", "reference_type", "reference_id"),
        {"schema": "pmrp_portfolio"},
    )

    journal_entry_id: Mapped[str] = mapped_column(Text, primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_event_id: Mapped[str] = mapped_column(Text, nullable=False)
    reference_type: Mapped[str] = mapped_column(Text, nullable=False)
    reference_id: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class JournalLineRow(StorageBase):
    """Double-entry accounting line grouped by journal entry."""

    __tablename__ = "journal_lines"
    __table_args__ = (
        Index("ix_journal_lines__account_currency", "account_code", "currency"),
        {"schema": "pmrp_portfolio"},
    )

    journal_entry_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey(
            "pmrp_portfolio.journal_entries.journal_entry_id",
            name="fk_journal_lines__journal_entry_id__journal_entries",
        ),
        primary_key=True,
    )
    line_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_code: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
