"""SQLAlchemy row model for durable dead-letter records."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from pmrp.storage.models.base import StorageBase


class DeadLetterRecordRow(StorageBase):
    """Durable consumer failure row with replay references."""

    __tablename__ = "dead_letter_records"
    __table_args__ = (
        Index(
            "ix_dead_letter_records__unresolved",
            "last_failed_at",
            postgresql_where=text("resolved_at IS NULL"),
        ),
        {"schema": "pmrp_ops"},
    )

    dead_letter_id: Mapped[str] = mapped_column(Text, primary_key=True)
    source_event_id: Mapped[str | None] = mapped_column(Text)
    source_command_id: Mapped[str | None] = mapped_column(Text)
    consumer_name: Mapped[str] = mapped_column(Text, nullable=False)
    failure_category: Mapped[str] = mapped_column(Text, nullable=False)
    exception_type: Mapped[str] = mapped_column(Text, nullable=False)
    exception_message: Mapped[str] = mapped_column(Text, nullable=False)
    first_failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_reference: Mapped[str] = mapped_column(Text, nullable=False)
    replayable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
