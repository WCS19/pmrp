"""SQLAlchemy row model for raw exchange records."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, LargeBinary, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pmrp.storage.models.base import StorageBase


class RawExchangeRecordRow(StorageBase):
    """Durable append-only raw exchange payload record."""

    __tablename__ = "exchange_records"
    __table_args__ = (
        CheckConstraint(
            """
            (
                payload_text IS NOT NULL
                AND payload_bytes IS NULL
            )
            OR (
                payload_text IS NULL
                AND payload_bytes IS NOT NULL
            )
            """,
            name="payload_storage",
        ),
        Index("ix_exchange_records__exchange_received", "exchange", "received_at"),
        Index("ix_exchange_records__channel_received", "channel", "received_at"),
        Index("ix_exchange_records__payload_hash", "payload_hash"),
        {
            "schema": "pmrp_raw",
            "postgresql_partition_by": "RANGE (received_at)",
        },
    )

    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    raw_record_id: Mapped[str] = mapped_column(Text, primary_key=True)
    exchange: Mapped[str] = mapped_column(Text, nullable=False)
    environment: Mapped[str] = mapped_column(Text, nullable=False)
    connection_id: Mapped[str | None] = mapped_column(Text)
    endpoint: Mapped[str | None] = mapped_column(Text)
    channel: Mapped[str | None] = mapped_column(Text)
    message_type: Mapped[str | None] = mapped_column(Text)
    exchange_occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sequence: Mapped[int | None] = mapped_column(BigInteger)
    content_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'application/json'"),
    )
    compression: Mapped[str | None] = mapped_column(Text)
    payload_text: Mapped[str | None] = mapped_column(Text)
    payload_bytes: Mapped[bytes | None] = mapped_column(LargeBinary)
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    parser_version: Mapped[str | None] = mapped_column(Text)
    transport_metadata: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    inserted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
