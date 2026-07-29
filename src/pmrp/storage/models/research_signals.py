"""SQLAlchemy row models for research signals and feature snapshots."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, Numeric, Text, desc
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pmrp.storage.models.base import StorageBase


class SignalRow(StorageBase):
    """Append-only strategy signal history row."""

    __tablename__ = "signals"
    __table_args__ = (
        CheckConstraint(
            "fair_probability IS NULL OR (fair_probability >= 0 AND fair_probability <= 1)",
            name="fair_probability",
        ),
        Index("ix_signals__strategy_time", "strategy_id", desc("generated_at")),
        Index("ix_signals__market_time", "market_id", desc("generated_at")),
        {
            "schema": "pmrp_research",
            "postgresql_partition_by": "RANGE (generated_at)",
        },
    )

    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    signal_id: Mapped[str] = mapped_column(Text, primary_key=True)
    strategy_id: Mapped[str] = mapped_column(Text, nullable=False)
    market_id: Mapped[str] = mapped_column(Text, nullable=False)
    contract_id: Mapped[str | None] = mapped_column(Text)
    outcome_id: Mapped[str | None] = mapped_column(Text)
    signal_type: Mapped[str] = mapped_column(Text, nullable=False)
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    strength: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    fair_probability: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    model_id: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str | None] = mapped_column(Text)
    feature_snapshot_id: Mapped[str | None] = mapped_column(Text)
    reason_code: Mapped[str] = mapped_column(Text, nullable=False)
    reason_text: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str] = mapped_column(Text, nullable=False)
    source_event_id: Mapped[str | None] = mapped_column(Text)


class FeatureSnapshotRow(StorageBase):
    """Versioned feature values and source-lineage row."""

    __tablename__ = "feature_snapshots"
    __table_args__ = (
        Index("ix_feature_snapshots__market_time", "market_id", desc("observed_at")),
        {
            "schema": "pmrp_research",
            "postgresql_partition_by": "RANGE (observed_at)",
        },
    )

    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    feature_snapshot_id: Mapped[str] = mapped_column(Text, primary_key=True)
    market_id: Mapped[str] = mapped_column(Text, nullable=False)
    strategy_id: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    calculation_version: Mapped[str] = mapped_column(Text, nullable=False)
    features: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    source_event_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
