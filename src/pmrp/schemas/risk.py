"""Canonical risk policy and decision schemas."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import Field, field_validator, model_validator

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.enums import RiskDecisionStatus
from pmrp.schemas.identifiers import CorrelationId, IntentId, RiskDecisionId
from pmrp.schemas.numeric import parse_decimal
from pmrp.schemas.time import UTCDateTime

_RISK_ID_MAX_LENGTH = 128
_RISK_TEXT_MAX_LENGTH = 1024


class RiskLimitScope(StrEnum):
    GLOBAL = "global"
    EXCHANGE = "exchange"
    ACCOUNT = "account"
    STRATEGY = "strategy"
    MARKET = "market"


class RiskLimit(CanonicalModel):
    risk_limit_id: str = Field(min_length=1, max_length=_RISK_ID_MAX_LENGTH)
    rule_id: str = Field(min_length=1, max_length=_RISK_ID_MAX_LENGTH)
    rule_version: str = Field(min_length=1, max_length=64)

    scope: RiskLimitScope
    scope_id: str | None = Field(default=None, min_length=1, max_length=256)

    limit_type: str = Field(min_length=1, max_length=_RISK_ID_MAX_LENGTH)
    limit_value: Decimal
    unit: str = Field(min_length=1, max_length=64)

    effective_at: UTCDateTime
    expires_at: UTCDateTime | None = None

    enabled: bool
    created_by: str = Field(min_length=1, max_length=_RISK_ID_MAX_LENGTH)
    approved_by: str | None = Field(default=None, min_length=1, max_length=_RISK_ID_MAX_LENGTH)

    @field_validator("limit_value", mode="before")
    @classmethod
    def parse_decimal_fields(cls, value: object) -> Decimal:
        return parse_decimal(value, field_name="risk limit decimal field")

    @model_validator(mode="after")
    def validate_effective_window(self) -> Self:
        if self.expires_at is not None and self.expires_at <= self.effective_at:
            msg = "expires_at must be after effective_at"
            raise ValueError(msg)
        return self


class RiskRuleResult(CanonicalModel):
    rule_id: str = Field(min_length=1, max_length=_RISK_ID_MAX_LENGTH)
    rule_version: str = Field(min_length=1, max_length=64)

    passed: bool
    reason_code: str = Field(min_length=1, max_length=_RISK_ID_MAX_LENGTH)
    reason_text: str | None = Field(default=None, min_length=1, max_length=_RISK_TEXT_MAX_LENGTH)

    observed_value: Decimal | None = None
    limit_value: Decimal | None = None
    unit: str | None = Field(default=None, min_length=1, max_length=64)

    evaluated_at: UTCDateTime

    @field_validator("observed_value", "limit_value", mode="before")
    @classmethod
    def parse_decimal_fields(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        return parse_decimal(value, field_name="risk rule result decimal field")


class RiskDecision(CanonicalModel):
    risk_decision_id: RiskDecisionId
    intent_id: IntentId

    status: RiskDecisionStatus
    evaluated_at: UTCDateTime

    input_snapshot_id: str = Field(min_length=1, max_length=_RISK_ID_MAX_LENGTH)
    rule_results: tuple[RiskRuleResult, ...]

    approved_quantity: Decimal | None = Field(default=None, gt=Decimal("0"))
    approved_limit_price: Decimal | None = Field(default=None, ge=Decimal("0"))
    approval_expires_at: UTCDateTime | None = None

    configuration_hash: str = Field(min_length=1, max_length=128)
    correlation_id: CorrelationId

    @field_validator("approved_quantity", "approved_limit_price", mode="before")
    @classmethod
    def parse_decimal_fields(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        return parse_decimal(value, field_name="risk decision decimal field")

    @model_validator(mode="after")
    def validate_approval_window(self) -> Self:
        if self.approval_expires_at is not None and self.approval_expires_at <= self.evaluated_at:
            msg = "approval_expires_at must be after evaluated_at"
            raise ValueError(msg)
        return self
