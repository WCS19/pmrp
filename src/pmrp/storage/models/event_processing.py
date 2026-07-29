"""SQLAlchemy row models for event processing infrastructure."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pmrp.storage.models.base import StorageBase


class ProcessedEventRow(StorageBase):
    """Consumer-level idempotency row for canonical event processing."""

    __tablename__ = "processed_events"
    __table_args__ = (
        Index("ix_processed_events__time", "processed_at"),
        {"schema": "pmrp_event"},
    )

    consumer_name: Mapped[str] = mapped_column(Text, primary_key=True)
    event_id: Mapped[str] = mapped_column(Text, primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    processing_version: Mapped[str | None] = mapped_column(Text)
    result_hash: Mapped[str | None] = mapped_column(Text)


class OutboxMessageRow(StorageBase):
    """Transactional outbox row for reliable event publication."""

    __tablename__ = "outbox_messages"
    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "topic",
            name="uq_outbox_messages__event_id_topic",
        ),
        Index(
            "ix_outbox_messages__pending",
            "available_at",
            "outbox_id",
            postgresql_where=text("published_at IS NULL"),
        ),
        {"schema": "pmrp_event"},
    )

    outbox_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    partition_key: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publish_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    last_error: Mapped[str | None] = mapped_column(Text)
