"""SQLAlchemy row models for account reconciliation storage."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKeyConstraint, Index, Integer, Text, desc, text
from sqlalchemy.orm import Mapped, mapped_column

from pmrp.storage.models.base import StorageBase


class ReconciliationRunRow(StorageBase):
    """Durable account reconciliation lifecycle row."""

    __tablename__ = "reconciliation_runs"
    __table_args__ = (
        Index(
            "ix_reconciliation_runs__account_time",
            "exchange",
            "account_id",
            desc("started_at"),
        ),
        {"schema": "pmrp_ops"},
    )

    reconciliation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    exchange: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, nullable=False)
    open_orders_checked: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    positions_checked: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    balances_checked: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    fills_checked: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    trading_gate_released: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    initiated_by: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class ReconciliationMismatchRow(StorageBase):
    """Difference between local and exchange-authoritative reconciliation state."""

    __tablename__ = "reconciliation_mismatches"
    __table_args__ = (
        ForeignKeyConstraint(
            ["reconciliation_id"],
            ["pmrp_ops.reconciliation_runs.reconciliation_id"],
            name="fk_reconciliation_mismatches__reconciliation_runs",
        ),
        Index("ix_reconciliation_mismatches__run", "reconciliation_id", "severity"),
        {"schema": "pmrp_ops"},
    )

    mismatch_id: Mapped[str] = mapped_column(Text, primary_key=True)
    reconciliation_id: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    local_value: Mapped[str | None] = mapped_column(Text)
    external_value: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text)
    requires_manual_review: Mapped[bool] = mapped_column(Boolean, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_note: Mapped[str | None] = mapped_column(Text)
