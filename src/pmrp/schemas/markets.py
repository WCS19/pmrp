"""Canonical market catalog schemas."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Self

from pydantic import Field, field_serializer, field_validator, model_validator

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.enums import MarketStatus, OutcomeType
from pmrp.schemas.identifiers import ContractId, EventId, MarketId, OutcomeId
from pmrp.schemas.immutability import freeze_string_mapping, thaw_string_mapping
from pmrp.schemas.numeric import parse_decimal, validate_currency
from pmrp.schemas.time import UTCDateTime


class Market(CanonicalModel):
    market_id: MarketId
    canonical_event_id: EventId | None = None

    exchange: str = Field(min_length=1, max_length=64)
    exchange_market_id: str = Field(min_length=1, max_length=256)
    exchange_event_id: str | None = Field(default=None, min_length=1, max_length=256)

    title: str = Field(min_length=1, max_length=512)
    subtitle: str | None = Field(default=None, min_length=1, max_length=512)
    description: str | None = Field(default=None, min_length=1, max_length=4096)
    category: str | None = Field(default=None, min_length=1, max_length=128)
    tags: tuple[str, ...] = ()

    outcome_type: OutcomeType
    status: MarketStatus

    opens_at: UTCDateTime | None = None
    closes_at: UTCDateTime | None = None
    resolves_at: UTCDateTime | None = None
    finalized_at: UTCDateTime | None = None

    currency: str = "USD"
    payout_per_unit: Decimal = Field(default=Decimal("1"), gt=Decimal("0"))

    tick_size: Decimal = Field(gt=Decimal("0"))
    quantity_increment: Decimal = Field(gt=Decimal("0"))

    rules_text: str | None = Field(default=None, min_length=1, max_length=8192)
    rules_url: str | None = Field(default=None, min_length=1, max_length=2048)

    created_at: UTCDateTime
    updated_at: UTCDateTime

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        return validate_currency(value)

    @field_validator("payout_per_unit", "tick_size", "quantity_increment", mode="before")
    @classmethod
    def parse_decimal_fields(cls, value: object) -> Decimal:
        return parse_decimal(value, field_name="market decimal field")

    @model_validator(mode="after")
    def validate_lifecycle_ordering(self) -> Self:
        if (
            self.opens_at is not None
            and self.closes_at is not None
            and self.closes_at < self.opens_at
        ):
            msg = "closes_at must not precede opens_at"
            raise ValueError(msg)
        return self


class Outcome(CanonicalModel):
    outcome_id: OutcomeId
    market_id: MarketId

    exchange_outcome_id: str | None = Field(default=None, min_length=1, max_length=256)

    name: str = Field(min_length=1, max_length=256)
    normalized_name: str = Field(min_length=1, max_length=256)
    index: int = Field(ge=0)

    is_tradeable: bool = True
    is_winning: bool | None = None

    payout_per_unit: Decimal = Field(default=Decimal("1"), gt=Decimal("0"))
    metadata: Mapping[str, str] = Field(default_factory=dict)

    @field_validator("payout_per_unit", mode="before")
    @classmethod
    def parse_payout_per_unit(cls, value: object) -> Decimal:
        return parse_decimal(value, field_name="Outcome.payout_per_unit")

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: Mapping[str, str]) -> Mapping[str, str]:
        return freeze_string_mapping(value, field_name="outcome metadata")

    @field_serializer("metadata")
    def serialize_metadata(self, value: Mapping[str, str]) -> dict[str, str]:
        return thaw_string_mapping(value)


class Contract(CanonicalModel):
    contract_id: ContractId
    market_id: MarketId
    outcome_id: OutcomeId

    exchange_contract_id: str | None = Field(default=None, min_length=1, max_length=256)

    symbol: str | None = Field(default=None, min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=256)

    tick_size: Decimal = Field(gt=Decimal("0"))
    quantity_increment: Decimal = Field(gt=Decimal("0"))
    min_order_quantity: Decimal | None = Field(default=None, ge=Decimal("0"))
    max_order_quantity: Decimal | None = Field(default=None, ge=Decimal("0"))

    active: bool
    created_at: UTCDateTime
    updated_at: UTCDateTime

    @field_validator(
        "tick_size",
        "quantity_increment",
        "min_order_quantity",
        "max_order_quantity",
        mode="before",
    )
    @classmethod
    def parse_decimal_fields(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        return parse_decimal(value, field_name="contract decimal field")

    @model_validator(mode="after")
    def validate_quantity_bounds(self) -> Self:
        if (
            self.min_order_quantity is not None
            and self.max_order_quantity is not None
            and self.max_order_quantity < self.min_order_quantity
        ):
            msg = "max_order_quantity must not be less than min_order_quantity"
            raise ValueError(msg)
        return self
