"""SQLAlchemy row models for deterministic replay and simulation storage."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
    Text,
    desc,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pmrp.storage.models.base import StorageBase


class ReplaySessionRow(StorageBase):
    """Deterministic replay manifest, state, progress, and checksum row."""

    __tablename__ = "replay_sessions"
    __table_args__ = (
        Index("ix_replay_sessions__state_created", "state", desc("created_at")),
        {"schema": "pmrp_research"},
    )

    replay_session_id: Mapped[str] = mapped_column(Text, primary_key=True)
    dataset_id: Mapped[str] = mapped_column(Text, nullable=False)
    dataset_checksum: Mapped[str] = mapped_column(Text, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    speed: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    deterministic: Mapped[bool] = mapped_column(Boolean, nullable=False)
    random_seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_ordering_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    strategy_versions: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    model_versions: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    configuration_hash: Mapped[str] = mapped_column(Text, nullable=False)
    code_commit: Mapped[str] = mapped_column(Text, nullable=False)
    dependency_lock_hash: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    current_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_events: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("0"),
    )
    rejected_events: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("0"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_checksum: Mapped[str | None] = mapped_column(Text)
    failure_message: Mapped[str | None] = mapped_column(Text)


class ReplayResultRow(StorageBase):
    """Completed replay summary and final portfolio row."""

    __tablename__ = "replay_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["replay_session_id"],
            ["pmrp_research.replay_sessions.replay_session_id"],
            name="fk_replay_results__replay_sessions",
        ),
        {"schema": "pmrp_research"},
    )

    replay_session_id: Mapped[str] = mapped_column(Text, primary_key=True)
    processed_events: Mapped[int] = mapped_column(BigInteger, nullable=False)
    generated_signals: Mapped[int] = mapped_column(BigInteger, nullable=False)
    generated_intents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    simulated_orders: Mapped[int] = mapped_column(BigInteger, nullable=False)
    simulated_fills: Mapped[int] = mapped_column(BigInteger, nullable=False)
    final_portfolio: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    metrics: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    result_checksum: Mapped[str] = mapped_column(Text, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SimulationSessionRow(StorageBase):
    """Simulation configuration and lifecycle row."""

    __tablename__ = "simulation_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["replay_session_id"],
            ["pmrp_research.replay_sessions.replay_session_id"],
            name="fk_simulation_sessions__replay_sessions",
        ),
        Index("ix_simulation_sessions__state_created", "state", desc("created_at")),
        {"schema": "pmrp_research"},
    )

    simulation_session_id: Mapped[str] = mapped_column(Text, primary_key=True)
    replay_session_id: Mapped[str | None] = mapped_column(Text)
    configuration: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    configuration_hash: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_checksum: Mapped[str | None] = mapped_column(Text)
