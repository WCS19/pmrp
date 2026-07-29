"""SQLAlchemy row models for exchange registry tables."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pmrp.storage.models.base import StorageBase


class ExchangeRow(StorageBase):
    """Durable registry row for configured exchanges."""

    __tablename__ = "exchanges"
    __table_args__ = ({"schema": "pmrp_core"},)

    exchange: Mapped[str] = mapped_column(Text, primary_key=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    capabilities: Mapped[dict[str, object]] = mapped_column(
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


class ExchangeAccountRow(StorageBase):
    """Durable account reference row without secret material."""

    __tablename__ = "exchange_accounts"
    __table_args__ = (
        Index("ix_exchange_accounts__exchange_environment", "exchange", "environment"),
        {"schema": "pmrp_core"},
    )

    account_id: Mapped[str] = mapped_column(Text, primary_key=True)
    exchange: Mapped[str] = mapped_column(
        Text,
        ForeignKey("pmrp_core.exchanges.exchange"),
        nullable=False,
    )
    environment: Mapped[str] = mapped_column(Text, nullable=False)
    external_account_id: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
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
