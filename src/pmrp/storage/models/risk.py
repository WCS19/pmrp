"""SQLAlchemy row models for risk policy, decision, and breach storage."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    desc,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pmrp.storage.models.base import StorageBase


class RiskLimitRow(StorageBase):
    """Versioned risk policy limit by scope."""

    __tablename__ = "risk_limits"
    __table_args__ = (
        Index(
            "ix_risk_limits__active_scope",
            "scope",
            "scope_id",
            "rule_id",
            postgresql_where=text("enabled = true"),
        ),
        {"schema": "pmrp_risk"},
    )

    risk_limit_id: Mapped[str] = mapped_column(Text, primary_key=True)
    rule_id: Mapped[str] = mapped_column(Text, nullable=False)
    rule_version: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    scope_id: Mapped[str | None] = mapped_column(Text)
    limit_type: Mapped[str] = mapped_column(Text, nullable=False)
    limit_value: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    approved_by: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    aggregate_version: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("0"),
    )


class RiskDecisionRow(StorageBase):
    """Immutable pre-trade risk rule evaluation result."""

    __tablename__ = "risk_decisions"
    __table_args__ = (
        Index("ix_risk_decisions__intent", "intent_id"),
        Index("ix_risk_decisions__status_time", "status", desc("evaluated_at")),
        {
            "schema": "pmrp_risk",
            "postgresql_partition_by": "RANGE (evaluated_at)",
        },
    )

    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    risk_decision_id: Mapped[str] = mapped_column(Text, primary_key=True)
    intent_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    input_snapshot_id: Mapped[str] = mapped_column(Text, nullable=False)
    approved_quantity: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    approved_limit_price: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    approval_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    configuration_hash: Mapped[str] = mapped_column(Text, nullable=False)
    correlation_id: Mapped[str] = mapped_column(Text, nullable=False)
    rule_results: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)


class RiskBreachRow(StorageBase):
    """Post-trade or operational risk breach record."""

    __tablename__ = "risk_breaches"
    __table_args__ = (
        Index(
            "ix_risk_breaches__open_severity",
            "severity",
            desc("detected_at"),
            postgresql_where=text("resolved_at IS NULL"),
        ),
        {"schema": "pmrp_risk"},
    )

    breach_id: Mapped[str] = mapped_column(Text, primary_key=True)
    rule_id: Mapped[str] = mapped_column(Text, nullable=False)
    rule_version: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    scope_id: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    limit_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    unit: Mapped[str | None] = mapped_column(Text)
    action_taken: Mapped[str] = mapped_column(Text, nullable=False)
    correlation_id: Mapped[str] = mapped_column(Text, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_note: Mapped[str | None] = mapped_column(Text)


class KillSwitchRow(StorageBase):
    """Durable scoped trading gate row."""

    __tablename__ = "kill_switches"
    __table_args__ = (
        Index(
            "uq_kill_switches__active_scope",
            "scope",
            text("COALESCE(scope_id, '')"),
            unique=True,
            postgresql_where=text("active = true"),
        ),
        {"schema": "pmrp_risk"},
    )

    kill_switch_id: Mapped[str] = mapped_column(Text, primary_key=True)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    scope_id: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_by: Mapped[str | None] = mapped_column(Text)
    activation_reason: Mapped[str | None] = mapped_column(Text)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_by: Mapped[str | None] = mapped_column(Text)
    release_reason: Mapped[str | None] = mapped_column(Text)
    aggregate_version: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("0"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class CapitalReservationRow(StorageBase):
    """Reservation preventing concurrent approvals from exceeding limits."""

    __tablename__ = "capital_reservations"
    __table_args__ = (
        UniqueConstraint("intent_id", name="uq_capital_reservations__intent_id"),
        Index(
            "ix_capital_reservations__active_expiry",
            "expires_at",
            postgresql_where=text("released_at IS NULL"),
        ),
        {"schema": "pmrp_risk"},
    )

    reservation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    intent_id: Mapped[str] = mapped_column(Text, nullable=False)
    strategy_id: Mapped[str] = mapped_column(Text, nullable=False)
    exchange: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[str] = mapped_column(Text, nullable=False)
    market_id: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    notional: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
