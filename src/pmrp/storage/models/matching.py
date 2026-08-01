"""SQLAlchemy row models for market relationship matching storage."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pmrp.storage.models.base import StorageBase


class MarketRelationshipRow(StorageBase):
    """Approved or reviewed relationship between canonical markets."""

    __tablename__ = "market_relationships"
    __table_args__ = (
        UniqueConstraint(
            "source_market_id",
            "target_market_id",
            "relationship_type",
            name="uq_market_relationships__source_target_type",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="confidence",
        ),
        Index(
            "ix_market_relationships__source_target",
            "source_market_id",
            "target_market_id",
        ),
        {"schema": "pmrp_research"},
    )

    relationship_id: Mapped[str] = mapped_column(Text, primary_key=True)
    source_market_id: Mapped[str] = mapped_column(Text, nullable=False)
    target_market_id: Mapped[str] = mapped_column(Text, nullable=False)
    relationship_type: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    validator_version: Mapped[str] = mapped_column(Text, nullable=False)
    settlement_rule_match: Mapped[bool | None] = mapped_column(Boolean)
    human_review_status: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    aggregate_version: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("0"),
    )
