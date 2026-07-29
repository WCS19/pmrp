"""SQLAlchemy row models for canonical event storage."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pmrp.storage.models.base import StorageBase


class EventIdRow(StorageBase):
    """Unpartitioned registry row for globally unique canonical event IDs."""

    __tablename__ = "event_ids"
    __table_args__ = ({"schema": "pmrp_event"},)

    event_id: Mapped[str] = mapped_column(Text, primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    inserted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class CanonicalEventRow(StorageBase):
    """Durable partitioned canonical event row for replay and audit."""

    __tablename__ = "canonical_events"
    __table_args__ = (
        CheckConstraint("schema_version >= 1", name="schema_version"),
        Index("ix_canonical_events__type_time", "event_type", "occurred_at"),
        Index(
            "ix_canonical_events__market_time",
            "market_id",
            "occurred_at",
            postgresql_where=text("market_id IS NOT NULL"),
        ),
        Index(
            "ix_canonical_events__order_time",
            "order_id",
            "occurred_at",
            postgresql_where=text("order_id IS NOT NULL"),
        ),
        Index("ix_canonical_events__correlation", "correlation_id"),
        {
            "schema": "pmrp_event",
            "postgresql_partition_by": "RANGE (occurred_at)",
        },
    )

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    event_id: Mapped[str] = mapped_column(Text, primary_key=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    producer: Mapped[str] = mapped_column(Text, nullable=False)
    exchange: Mapped[str | None] = mapped_column(Text)
    market_id: Mapped[str | None] = mapped_column(Text)
    account_id: Mapped[str | None] = mapped_column(Text)
    strategy_id: Mapped[str | None] = mapped_column(Text)
    order_id: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str] = mapped_column(Text, nullable=False)
    causation_id: Mapped[str | None] = mapped_column(Text)
    trace_id: Mapped[str | None] = mapped_column(Text)
    replay_session_id: Mapped[str | None] = mapped_column(Text)
    simulation_session_id: Mapped[str | None] = mapped_column(Text)
    quality_flags: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{}'::text[]"),
    )
    attributes: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    inserted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
