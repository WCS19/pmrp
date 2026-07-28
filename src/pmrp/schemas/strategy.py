"""Canonical strategy and signal schemas."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import Field, field_validator, model_validator

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.identifiers import (
    ContractId,
    CorrelationId,
    FeatureSnapshotId,
    MarketId,
    ModelId,
    OutcomeId,
    SignalId,
    StrategyId,
)
from pmrp.schemas.numeric import parse_decimal
from pmrp.schemas.time import UTCDateTime


class SignalDirection(StrEnum):
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"
    BUY = "buy"
    SELL = "sell"


class Signal(CanonicalModel):
    signal_id: SignalId
    strategy_id: StrategyId

    market_id: MarketId
    contract_id: ContractId | None = None
    outcome_id: OutcomeId | None = None

    signal_type: str = Field(min_length=1, max_length=128)
    direction: SignalDirection

    strength: Decimal | None = None
    fair_probability: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("1"))
    confidence: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("1"))

    valid_from: UTCDateTime
    valid_until: UTCDateTime | None = None

    model_id: ModelId | None = None
    model_version: str | None = Field(default=None, min_length=1, max_length=128)
    feature_snapshot_id: FeatureSnapshotId | None = None

    reason_code: str = Field(min_length=1, max_length=128)
    reason_text: str | None = Field(default=None, min_length=1, max_length=1024)

    correlation_id: CorrelationId

    @field_validator("strength", "fair_probability", "confidence", mode="before")
    @classmethod
    def parse_decimal_fields(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        return parse_decimal(value, field_name="signal decimal field")

    @model_validator(mode="after")
    def validate_validity_window(self) -> Self:
        if self.valid_until is not None and self.valid_until <= self.valid_from:
            msg = "valid_until must be after valid_from"
            raise ValueError(msg)
        return self
