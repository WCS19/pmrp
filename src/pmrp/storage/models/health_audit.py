"""SQLAlchemy row models for adapter health and operator audit storage."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, Text, desc
from sqlalchemy.orm import Mapped, mapped_column

from pmrp.storage.models.base import StorageBase


class AdapterHealthSnapshotRow(StorageBase):
    """Time-series adapter connectivity and trading-gate health snapshot."""

    __tablename__ = "adapter_health_snapshots"
    __table_args__ = (
        Index("ix_adapter_health__exchange_time", "exchange", desc("captured_at")),
        {
            "schema": "pmrp_ops",
            "postgresql_partition_by": "RANGE (captured_at)",
        },
    )

    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    exchange: Mapped[str] = mapped_column(Text, primary_key=True)
    environment: Mapped[str] = mapped_column(Text, primary_key=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    connected: Mapped[bool] = mapped_column(Boolean, nullable=False)
    authenticated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    subscriptions_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_reconciliation_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    market_data_fresh: Mapped[bool] = mapped_column(Boolean, nullable=False)
    trading_gate_open: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reconnect_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    message: Mapped[str | None] = mapped_column(Text)


class OperatorAuditRecordRow(StorageBase):
    """Immutable operator and API control audit history row."""

    __tablename__ = "operator_audit_records"
    __table_args__ = (
        Index("ix_operator_audit__actor_time", "actor", desc("requested_at")),
        Index(
            "ix_operator_audit__scope_time",
            "scope",
            "scope_id",
            desc("requested_at"),
        ),
        {
            "schema": "pmrp_audit",
            "postgresql_partition_by": "RANGE (requested_at)",
        },
    )

    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    audit_id: Mapped[str] = mapped_column(Text, primary_key=True)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    scope_id: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str] = mapped_column(Text, nullable=False)
    request_id: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(Text)
    source_ip_hash: Mapped[str | None] = mapped_column(Text)
    request_hash: Mapped[str | None] = mapped_column(Text)
