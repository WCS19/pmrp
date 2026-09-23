"""Canonical risk policy and decision schemas."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import Field, field_validator, model_validator

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.enums import RiskDecisionStatus
from pmrp.schemas.identifiers import (
    AccountId,
    CorrelationId,
    IntentId,
    MarketId,
    RiskDecisionId,
    StrategyId,
)
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


class RiskInputSnapshot(CanonicalModel):
    risk_input_snapshot_id: str = Field(min_length=1, max_length=_RISK_ID_MAX_LENGTH)
    captured_at: UTCDateTime

    strategy_id: StrategyId
    exchange: str = Field(min_length=1, max_length=64)
    account_id: AccountId
    market_id: MarketId

    current_position: Decimal
    open_order_quantity: Decimal = Field(ge=Decimal("0"))
    available_balance: Decimal = Field(ge=Decimal("0"))

    gross_exposure: Decimal = Field(ge=Decimal("0"))
    net_exposure: Decimal
    daily_realized_pnl: Decimal
    daily_unrealized_pnl: Decimal

    market_data_age_ms: int = Field(ge=0)
    reconciliation_healthy: bool
    kill_switch_clear: bool

    @field_validator(
        "current_position",
        "open_order_quantity",
        "available_balance",
        "gross_exposure",
        "net_exposure",
        "daily_realized_pnl",
        "daily_unrealized_pnl",
        mode="before",
    )
    @classmethod
    def parse_decimal_fields(cls, value: object) -> Decimal:
        return parse_decimal(value, field_name="risk input snapshot decimal field")


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
    def validate_decision_state(self) -> Self:
        if not self.rule_results:
            msg = "risk decision requires at least one rule result"
            raise ValueError(msg)

        approved_fields = (
            self.approved_quantity,
            self.approved_limit_price,
            self.approval_expires_at,
        )
        has_approval = any(value is not None for value in approved_fields)

        if self.status is RiskDecisionStatus.APPROVED:
            if any(not result.passed for result in self.rule_results):
                msg = "approved risk decision cannot contain failed rule results"
                raise ValueError(msg)
            if self.approved_quantity is None or self.approved_limit_price is None:
                msg = "approved risk decision requires approved quantity and limit price"
                raise ValueError(msg)
        elif has_approval:
            msg = "non-approved risk decision cannot contain approval fields"
            raise ValueError(msg)
        elif all(result.passed for result in self.rule_results):
            msg = "non-approved risk decision requires at least one failed rule result"
            raise ValueError(msg)

        if self.approval_expires_at is not None and self.approval_expires_at <= self.evaluated_at:
            msg = "approval_expires_at must be after evaluated_at"
            raise ValueError(msg)
        return self


class RiskBreach(CanonicalModel):
    breach_id: str = Field(min_length=1, max_length=_RISK_ID_MAX_LENGTH)
    rule_id: str = Field(min_length=1, max_length=_RISK_ID_MAX_LENGTH)
    rule_version: str = Field(min_length=1, max_length=64)

    scope: RiskLimitScope
    scope_id: str | None = Field(default=None, min_length=1, max_length=256)

    severity: str = Field(min_length=1, max_length=64)
    detected_at: UTCDateTime

    observed_value: Decimal | None = None
    limit_value: Decimal | None = None
    unit: str | None = Field(default=None, min_length=1, max_length=64)

    action_taken: str = Field(min_length=1, max_length=_RISK_ID_MAX_LENGTH)
    correlation_id: CorrelationId

    @field_validator("observed_value", "limit_value", mode="before")
    @classmethod
    def parse_decimal_fields(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        return parse_decimal(value, field_name="risk breach decimal field")


class KillSwitchScope(StrEnum):
    GLOBAL = "global"
    EXCHANGE = "exchange"
    ACCOUNT = "account"
    STRATEGY = "strategy"
    MARKET = "market"
    EXECUTION_GATEWAY = "execution_gateway"


class KillSwitchState(CanonicalModel):
    kill_switch_id: str = Field(min_length=1, max_length=_RISK_ID_MAX_LENGTH)
    scope: KillSwitchScope
    scope_id: str | None = Field(default=None, min_length=1, max_length=256)

    active: bool
    activated_at: UTCDateTime | None = None
    activated_by: str | None = Field(default=None, min_length=1, max_length=_RISK_ID_MAX_LENGTH)
    activation_reason: str | None = Field(
        default=None, min_length=1, max_length=_RISK_TEXT_MAX_LENGTH
    )

    released_at: UTCDateTime | None = None
    released_by: str | None = Field(default=None, min_length=1, max_length=_RISK_ID_MAX_LENGTH)
    release_reason: str | None = Field(default=None, min_length=1, max_length=_RISK_TEXT_MAX_LENGTH)

    version: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_activation_lifecycle(self) -> Self:
        activation_fields = (
            self.activated_at,
            self.activated_by,
            self.activation_reason,
        )
        release_fields = (
            self.released_at,
            self.released_by,
            self.release_reason,
        )
        has_activation = any(value is not None for value in activation_fields)
        has_release = any(value is not None for value in release_fields)

        if self.active and not all(value is not None for value in activation_fields):
            msg = "active kill switch requires activation audit fields"
            raise ValueError(msg)
        if self.active and has_release:
            msg = "active kill switch cannot contain release fields"
            raise ValueError(msg)

        if (
            not self.active
            and has_release
            and not all(value is not None for value in release_fields)
        ):
            msg = "released kill switch requires release audit fields"
            raise ValueError(msg)
        if (
            not self.active
            and has_release
            and not all(value is not None for value in activation_fields)
        ):
            msg = "released kill switch requires activation audit fields"
            raise ValueError(msg)
        if not self.active and has_activation and not has_release:
            msg = "inactive activated kill switch requires release audit fields"
            raise ValueError(msg)

        if (
            self.released_at is not None
            and self.activated_at is not None
            and self.released_at <= self.activated_at
        ):
            msg = "released_at must be after activated_at"
            raise ValueError(msg)
        return self
