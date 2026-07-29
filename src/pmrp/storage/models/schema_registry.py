"""SQLAlchemy row model for pmrp_core.schema_registry."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from pmrp.storage.models.base import StorageBase


class SchemaRegistryRow(StorageBase):
    """Durable registry row for canonical schema metadata."""

    __tablename__ = "schema_registry"
    __table_args__ = (
        CheckConstraint("schema_version >= 1", name="schema_version"),
        Index("ix_schema_registry__category", "schema_category"),
        {"schema": "pmrp_core"},
    )

    schema_name: Mapped[str] = mapped_column(Text, primary_key=True)
    schema_version: Mapped[int] = mapped_column(Integer, primary_key=True)
    schema_category: Mapped[str] = mapped_column(Text, nullable=False)
    python_model_path: Mapped[str] = mapped_column(Text, nullable=False)
    json_schema_uri: Mapped[str | None] = mapped_column(Text)
    introduced_in_platform_version: Mapped[str] = mapped_column(Text, nullable=False)
    deprecated_in_platform_version: Mapped[str | None] = mapped_column(Text)
    backward_compatible_with: Mapped[list[int]] = mapped_column(
        ARRAY(Integer),
        nullable=False,
        server_default=text("'{}'::integer[]"),
    )
    upcaster_paths: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{}'::text[]"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
