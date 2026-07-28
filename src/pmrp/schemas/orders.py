"""Canonical order intent and approval schemas."""

from __future__ import annotations

from decimal import Decimal
from typing import Self

from pydantic import Field, field_validator, model_validator

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.enums import OrderType, Side, TimeInForce
from pmrp.schemas.identifiers import (
    AccountId,
    ContractId,
    CorrelationId,
    IntentId,
    MarketId,
    OrderId,
    OutcomeId,
    RiskDecisionId,
    SignalId,
    StrategyId,
)
from pmrp.schemas.numeric import parse_decimal
from pmrp.schemas.time import UTCDateTime

_OPAQUE_ORDER_REF_MAX_LENGTH = 256


class OrderIntent(CanonicalModel):
    intent_id: IntentId
    strategy_id: StrategyId

    market_id: MarketId
    contract_id: ContractId
    outcome_id: OutcomeId

    side: Side
    quantity: Decimal = Field(gt=Decimal("0"))
    limit_price: Decimal | None = Field(default=None, ge=Decimal("0"))

    order_type: OrderType = OrderType.LIMIT
    time_in_force: TimeInForce = TimeInForce.GTC

    post_only: bool = False
    reduce_only: bool = False

    urgency: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("1"))

    created_at: UTCDateTime
    expires_at: UTCDateTime | None = None

    signal_ids: tuple[SignalId, ...] = ()
    correlation_id: CorrelationId
    idempotency_key: str = Field(min_length=1, max_length=_OPAQUE_ORDER_REF_MAX_LENGTH)

    @field_validator("quantity", "limit_price", "urgency", mode="before")
    @classmethod
    def parse_decimal_fields(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        return parse_decimal(value, field_name="order intent decimal field")

    @model_validator(mode="after")
    def validate_order_constraints(self) -> Self:
        _validate_order_pricing(self.order_type, self.limit_price, self.post_only)
        _validate_expiry(self.created_at, self.expires_at, field_name="expires_at")
        return self


class ApprovedOrder(CanonicalModel):
    order_id: OrderId
    intent_id: IntentId
    strategy_id: StrategyId

    risk_decision_id: RiskDecisionId

    exchange: str = Field(min_length=1, max_length=64)
    account_id: AccountId

    market_id: MarketId
    contract_id: ContractId
    outcome_id: OutcomeId

    side: Side
    quantity: Decimal = Field(gt=Decimal("0"))
    limit_price: Decimal | None = Field(default=None, ge=Decimal("0"))

    order_type: OrderType
    time_in_force: TimeInForce

    post_only: bool
    reduce_only: bool

    approved_at: UTCDateTime
    approval_expires_at: UTCDateTime | None = None

    client_order_id: str = Field(min_length=1, max_length=_OPAQUE_ORDER_REF_MAX_LENGTH)
    idempotency_key: str = Field(min_length=1, max_length=_OPAQUE_ORDER_REF_MAX_LENGTH)
    correlation_id: CorrelationId

    @field_validator("quantity", "limit_price", mode="before")
    @classmethod
    def parse_decimal_fields(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        return parse_decimal(value, field_name="approved order decimal field")

    @model_validator(mode="after")
    def validate_order_constraints(self) -> Self:
        _validate_order_pricing(self.order_type, self.limit_price, self.post_only)
        _validate_expiry(
            self.approved_at,
            self.approval_expires_at,
            field_name="approval_expires_at",
        )
        return self


def _validate_order_pricing(
    order_type: OrderType,
    limit_price: Decimal | None,
    post_only: bool,
) -> None:
    if order_type is OrderType.LIMIT and limit_price is None:
        msg = "limit orders require limit_price"
        raise ValueError(msg)
    if order_type is OrderType.MARKET and post_only:
        msg = "post_only is invalid for market orders"
        raise ValueError(msg)


def _validate_expiry(
    starts_at: UTCDateTime,
    expires_at: UTCDateTime | None,
    *,
    field_name: str,
) -> None:
    if expires_at is not None and expires_at <= starts_at:
        msg = f"{field_name} must be after the creation timestamp"
        raise ValueError(msg)
