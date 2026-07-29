"""SQLAlchemy row models for research strategy and model metadata."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    desc,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pmrp.storage.models.base import StorageBase


class StrategyDefinitionRow(StorageBase):
    """Versioned strategy implementation metadata row."""

    __tablename__ = "strategy_definitions"
    __table_args__ = ({"schema": "pmrp_research"},)

    strategy_type: Mapped[str] = mapped_column(Text, primary_key=True)
    strategy_version: Mapped[str] = mapped_column(Text, primary_key=True)
    implementation_path: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    configuration_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    subscribed_event_types: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    supports_replay: Mapped[bool] = mapped_column(Boolean, nullable=False)
    supports_simulation: Mapped[bool] = mapped_column(Boolean, nullable=False)
    supports_paper: Mapped[bool] = mapped_column(Boolean, nullable=False)
    supports_shadow: Mapped[bool] = mapped_column(Boolean, nullable=False)
    supports_live: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class StrategyInstanceRow(StorageBase):
    """Configured strategy lifecycle and health row."""

    __tablename__ = "strategy_instances"
    __table_args__ = (
        ForeignKeyConstraint(
            ["strategy_type", "strategy_version"],
            [
                "pmrp_research.strategy_definitions.strategy_type",
                "pmrp_research.strategy_definitions.strategy_version",
            ],
            name="fk_strategy_instances__type_version__strategy_definitions",
        ),
        Index("ix_strategy_instances__state_health", "state", "health_status"),
        {"schema": "pmrp_research"},
    )

    strategy_id: Mapped[str] = mapped_column(Text, primary_key=True)
    strategy_type: Mapped[str] = mapped_column(Text, nullable=False)
    strategy_version: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    environment: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    configuration_version: Mapped[int] = mapped_column(Integer, nullable=False)
    configuration_hash: Mapped[str] = mapped_column(Text, nullable=False)
    capital_allocation_amount: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    capital_allocation_currency: Mapped[str | None] = mapped_column(Text)
    health_status: Mapped[str] = mapped_column(Text, nullable=False)
    health_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    aggregate_version: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("0"),
    )


class StrategyConfigurationRow(StorageBase):
    """Immutable strategy configuration version and approval row."""

    __tablename__ = "strategy_configurations"
    __table_args__ = (
        UniqueConstraint(
            "strategy_id",
            "configuration_hash",
            name="uq_strategy_configurations__strategy_id_configuration_hash",
        ),
        {"schema": "pmrp_research"},
    )

    strategy_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("pmrp_research.strategy_instances.strategy_id"),
        primary_key=True,
    )
    configuration_version: Mapped[int] = mapped_column(Integer, primary_key=True)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    configuration: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    configuration_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    approved_by: Mapped[str | None] = mapped_column(Text)
    approval_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class ModelArtifactRow(StorageBase):
    """Model artifact metadata and approval state row."""

    __tablename__ = "model_artifacts"
    __table_args__ = (
        Index("ix_model_artifacts__approval", "approval_status", desc("trained_at")),
        {"schema": "pmrp_research"},
    )

    model_id: Mapped[str] = mapped_column(Text, primary_key=True)
    model_version: Mapped[str] = mapped_column(Text, primary_key=True)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_uri: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_checksum: Mapped[str] = mapped_column(Text, nullable=False)
    training_dataset_id: Mapped[str] = mapped_column(Text, nullable=False)
    training_dataset_checksum: Mapped[str] = mapped_column(Text, nullable=False)
    training_code_commit: Mapped[str] = mapped_column(Text, nullable=False)
    dependency_lock_hash: Mapped[str] = mapped_column(Text, nullable=False)
    feature_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    target_definition: Mapped[str] = mapped_column(Text, nullable=False)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    random_seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    evaluation_metrics: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    calibration_method: Mapped[str | None] = mapped_column(Text)
    approval_status: Mapped[str] = mapped_column(Text, nullable=False)
    approved_by: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
