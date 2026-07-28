"""Canonical market-data schemas."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import Field, field_validator, model_validator

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.enums import LiquidityRole, Side
from pmrp.schemas.identifiers import ContractId, MarketId, OutcomeId
from pmrp.schemas.numeric import parse_decimal
from pmrp.schemas.time import UTCDateTime


class OrderBookLevel(CanonicalModel):
    price: Decimal = Field(ge=Decimal("0"))
    quantity: Decimal = Field(ge=Decimal("0"))
    order_count: int | None = Field(default=None, ge=0)

    @field_validator("price", "quantity", mode="before")
    @classmethod
    def parse_decimal_fields(cls, value: object) -> Decimal:
        return parse_decimal(value, field_name="order book level decimal field")


class OrderBookSnapshot(CanonicalModel):
    market_id: MarketId
    contract_id: ContractId
    exchange: str = Field(min_length=1, max_length=64)

    sequence: int | None = Field(default=None, ge=0)
    exchange_occurred_at: UTCDateTime | None = None
    received_at: UTCDateTime

    bids: tuple[OrderBookLevel, ...]
    asks: tuple[OrderBookLevel, ...]

    is_valid: bool = True
    snapshot_reason: str = Field(default="initial", min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_book_ordering(self) -> Self:
        if not _strictly_descending(level.price for level in self.bids):
            msg = "bid prices must be strictly descending"
            raise ValueError(msg)
        if not _strictly_ascending(level.price for level in self.asks):
            msg = "ask prices must be strictly ascending"
            raise ValueError(msg)
        return self


class OrderBookDeltaAction(StrEnum):
    UPSERT = "upsert"
    DELETE = "delete"


class OrderBookDeltaLevel(CanonicalModel):
    side: Side
    price: Decimal = Field(ge=Decimal("0"))
    quantity: Decimal = Field(ge=Decimal("0"))
    action: OrderBookDeltaAction

    @field_validator("price", "quantity", mode="before")
    @classmethod
    def parse_decimal_fields(cls, value: object) -> Decimal:
        return parse_decimal(value, field_name="order book delta decimal field")


class OrderBookDelta(CanonicalModel):
    market_id: MarketId
    contract_id: ContractId
    exchange: str = Field(min_length=1, max_length=64)

    sequence: int | None = Field(default=None, ge=0)
    previous_sequence: int | None = Field(default=None, ge=0)

    exchange_occurred_at: UTCDateTime | None = None
    received_at: UTCDateTime

    changes: tuple[OrderBookDeltaLevel, ...]


class Trade(CanonicalModel):
    trade_id: str = Field(min_length=1, max_length=128)
    exchange: str = Field(min_length=1, max_length=64)
    exchange_trade_id: str = Field(min_length=1, max_length=256)

    market_id: MarketId
    contract_id: ContractId
    outcome_id: OutcomeId

    price: Decimal = Field(ge=Decimal("0"))
    quantity: Decimal = Field(gt=Decimal("0"))

    aggressor_side: Side | None = None
    liquidity_role: LiquidityRole = LiquidityRole.UNKNOWN

    exchange_occurred_at: UTCDateTime
    received_at: UTCDateTime

    sequence: int | None = Field(default=None, ge=0)

    @field_validator("price", "quantity", mode="before")
    @classmethod
    def parse_decimal_fields(cls, value: object) -> Decimal:
        return parse_decimal(value, field_name="trade decimal field")


def _strictly_descending(values: Iterable[Decimal]) -> bool:
    previous: Decimal | None = None
    for value in values:
        if previous is not None and value >= previous:
            return False
        previous = value
    return True


def _strictly_ascending(values: Iterable[Decimal]) -> bool:
    previous: Decimal | None = None
    for value in values:
        if previous is not None and value <= previous:
            return False
        previous = value
    return True
