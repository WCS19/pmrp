"""Canonical portfolio, accounting, settlement, and reconciliation schemas."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import Field, field_validator, model_validator

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.identifiers import (
    AccountId,
    ContractId,
    EventId,
    FillId,
    MarketId,
    OutcomeId,
    PositionId,
    SettlementId,
    StrategyId,
)
from pmrp.schemas.numeric import Money, parse_decimal, validate_currency
from pmrp.schemas.time import UTCDateTime

_PORTFOLIO_ID_MAX_LENGTH = 128
_PORTFOLIO_TEXT_MAX_LENGTH = 1024


class Position(CanonicalModel):
    position_id: PositionId

    exchange: str = Field(min_length=1, max_length=64)
    account_id: AccountId

    market_id: MarketId
    contract_id: ContractId
    outcome_id: OutcomeId

    quantity: Decimal
    average_entry_price: Decimal | None = Field(default=None, ge=Decimal("0"))

    realized_pnl: Money
    unrealized_pnl: Money

    fees_paid: Money
    rebates_received: Money

    opened_at: UTCDateTime | None = None
    last_updated_at: UTCDateTime

    aggregate_version: int = Field(ge=0)

    @field_validator("quantity", "average_entry_price", mode="before")
    @classmethod
    def parse_decimal_fields(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        return parse_decimal(value, field_name="position decimal field")

    @model_validator(mode="after")
    def validate_position_state(self) -> Self:
        if self.opened_at is not None and self.last_updated_at < self.opened_at:
            msg = "last_updated_at must not be before opened_at"
            raise ValueError(msg)
        if self.fees_paid.amount < Decimal("0"):
            msg = "fees_paid amount must be nonnegative"
            raise ValueError(msg)
        if self.rebates_received.amount < Decimal("0"):
            msg = "rebates_received amount must be nonnegative"
            raise ValueError(msg)
        return self


class PositionLot(CanonicalModel):
    lot_id: str = Field(min_length=1, max_length=_PORTFOLIO_ID_MAX_LENGTH)
    position_id: PositionId

    source_fill_id: FillId
    quantity: Decimal
    remaining_quantity: Decimal

    entry_price: Decimal = Field(ge=Decimal("0"))
    opened_at: UTCDateTime

    strategy_id: StrategyId | None = None

    @field_validator("quantity", "remaining_quantity", "entry_price", mode="before")
    @classmethod
    def parse_decimal_fields(cls, value: object) -> Decimal:
        return parse_decimal(value, field_name="position lot decimal field")

    @model_validator(mode="after")
    def validate_lot_quantities(self) -> Self:
        if self.quantity == Decimal("0"):
            msg = "position lot quantity must be nonzero"
            raise ValueError(msg)
        if abs(self.remaining_quantity) > abs(self.quantity):
            msg = "remaining_quantity magnitude must not exceed quantity magnitude"
            raise ValueError(msg)
        if self.remaining_quantity != Decimal("0") and (self.remaining_quantity > Decimal("0")) != (
            self.quantity > Decimal("0")
        ):
            msg = "remaining_quantity sign must match quantity sign"
            raise ValueError(msg)
        return self


class CashBalance(CanonicalModel):
    balance_id: str = Field(min_length=1, max_length=_PORTFOLIO_ID_MAX_LENGTH)

    exchange: str = Field(min_length=1, max_length=64)
    account_id: AccountId
    currency: str

    available: Decimal
    reserved: Decimal
    total: Decimal

    captured_at: UTCDateTime

    @field_validator("available", "reserved", "total", mode="before")
    @classmethod
    def parse_decimal_fields(cls, value: object) -> Decimal:
        return parse_decimal(value, field_name="cash balance decimal field")

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        return validate_currency(value)

    @model_validator(mode="after")
    def validate_balance_identity(self) -> Self:
        if self.available + self.reserved != self.total:
            msg = "available plus reserved must equal total"
            raise ValueError(msg)
        return self


class PortfolioSnapshot(CanonicalModel):
    portfolio_id: str = Field(min_length=1, max_length=_PORTFOLIO_ID_MAX_LENGTH)
    captured_at: UTCDateTime

    positions: tuple[Position, ...]
    balances: tuple[CashBalance, ...]

    realized_pnl: tuple[Money, ...]
    unrealized_pnl: tuple[Money, ...]

    gross_exposure: tuple[Money, ...]
    net_exposure: tuple[Money, ...]

    reconciliation_status: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_snapshot_identity(self) -> Self:
        _reject_duplicate_strings(
            (position.position_id for position in self.positions),
            field_name="positions",
        )
        _reject_duplicate_strings(
            (balance.balance_id for balance in self.balances),
            field_name="balances",
        )
        return self


class JournalLine(CanonicalModel):
    account_code: str = Field(min_length=1, max_length=_PORTFOLIO_ID_MAX_LENGTH)
    amount: Decimal
    currency: str
    description: str | None = Field(default=None, min_length=1, max_length=512)

    @field_validator("amount", mode="before")
    @classmethod
    def parse_amount(cls, value: object) -> Decimal:
        return parse_decimal(value, field_name="journal line amount")

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        return validate_currency(value)


class AccountingJournalEntry(CanonicalModel):
    journal_entry_id: str = Field(min_length=1, max_length=_PORTFOLIO_ID_MAX_LENGTH)
    occurred_at: UTCDateTime

    source_event_id: EventId
    reference_type: str = Field(min_length=1, max_length=64)
    reference_id: str = Field(min_length=1, max_length=_PORTFOLIO_ID_MAX_LENGTH)

    lines: tuple[JournalLine, ...]
    description: str = Field(min_length=1, max_length=_PORTFOLIO_TEXT_MAX_LENGTH)

    created_at: UTCDateTime

    @model_validator(mode="after")
    def validate_journal_balance(self) -> Self:
        if not self.lines:
            msg = "journal entry requires at least one line"
            raise ValueError(msg)
        if self.created_at < self.occurred_at:
            msg = "created_at must not be before occurred_at"
            raise ValueError(msg)
        totals_by_currency: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        for line in self.lines:
            totals_by_currency[line.currency] += line.amount
        unbalanced_currencies = [
            currency for currency, total in totals_by_currency.items() if total != Decimal("0")
        ]
        if unbalanced_currencies:
            msg = "journal lines must balance to zero by currency"
            raise ValueError(msg)
        return self


class PnlAttribution(CanonicalModel):
    attribution_id: str = Field(min_length=1, max_length=_PORTFOLIO_ID_MAX_LENGTH)

    strategy_id: StrategyId | None = None
    market_id: MarketId | None = None
    exchange: str | None = Field(default=None, min_length=1, max_length=64)

    starts_at: UTCDateTime
    ends_at: UTCDateTime

    realized_trading_pnl: Money
    unrealized_pnl_change: Money
    fees: Money
    rebates: Money
    slippage: Money | None = None
    settlement_pnl: Money | None = None

    total_pnl: Money
    calculation_version: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if self.ends_at <= self.starts_at:
            msg = "ends_at must be after starts_at"
            raise ValueError(msg)
        return self


class SettlementStatus(StrEnum):
    UNRESOLVED = "unresolved"
    PENDING_RESOLUTION = "pending_resolution"
    RESOLVED = "resolved"
    DISPUTED = "disputed"
    FINALIZED = "finalized"
    SETTLED = "settled"
    CORRECTED = "corrected"


class Settlement(CanonicalModel):
    settlement_id: SettlementId
    market_id: MarketId
    exchange: str = Field(min_length=1, max_length=64)

    status: SettlementStatus
    winning_outcome_ids: tuple[OutcomeId, ...]

    resolved_at: UTCDateTime | None = None
    finalized_at: UTCDateTime | None = None
    settled_at: UTCDateTime | None = None

    payout_per_unit: Decimal | None = Field(default=None, ge=Decimal("0"))
    source: str = Field(min_length=1, max_length=128)
    source_reference: str | None = Field(
        default=None,
        min_length=1,
        max_length=_PORTFOLIO_ID_MAX_LENGTH,
    )

    correction_of_settlement_id: SettlementId | None = None

    @field_validator("payout_per_unit", mode="before")
    @classmethod
    def parse_decimal_fields(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        return parse_decimal(value, field_name="settlement decimal field")

    @model_validator(mode="after")
    def validate_settlement_lifecycle(self) -> Self:
        if self.finalized_at is not None and self.resolved_at is None:
            msg = "finalized settlement requires resolved_at"
            raise ValueError(msg)
        if self.settled_at is not None and self.finalized_at is None:
            msg = "settled settlement requires finalized_at"
            raise ValueError(msg)
        if (
            self.finalized_at is not None
            and self.resolved_at is not None
            and self.finalized_at < self.resolved_at
        ):
            msg = "finalized_at must not be before resolved_at"
            raise ValueError(msg)
        if (
            self.settled_at is not None
            and self.finalized_at is not None
            and self.settled_at < self.finalized_at
        ):
            msg = "settled_at must not be before finalized_at"
            raise ValueError(msg)
        if self.status is SettlementStatus.CORRECTED and self.correction_of_settlement_id is None:
            msg = "corrected settlement requires correction_of_settlement_id"
            raise ValueError(msg)
        return self


class ReconciliationStatus(StrEnum):
    HEALTHY = "healthy"
    MISMATCH = "mismatch"
    UNKNOWN = "unknown"
    FAILED = "failed"


class ReconciliationMismatch(CanonicalModel):
    mismatch_id: str = Field(min_length=1, max_length=_PORTFOLIO_ID_MAX_LENGTH)
    category: str = Field(min_length=1, max_length=64)

    local_value: str | None = Field(default=None, min_length=1, max_length=512)
    external_value: str | None = Field(default=None, min_length=1, max_length=512)

    severity: str = Field(min_length=1, max_length=64)
    explanation: str | None = Field(default=None, min_length=1, max_length=1024)
    requires_manual_review: bool


class ReconciliationResult(CanonicalModel):
    reconciliation_id: str = Field(min_length=1, max_length=_PORTFOLIO_ID_MAX_LENGTH)
    exchange: str = Field(min_length=1, max_length=64)
    account_id: AccountId

    started_at: UTCDateTime
    completed_at: UTCDateTime

    status: ReconciliationStatus
    mismatches: tuple[ReconciliationMismatch, ...]

    open_orders_checked: int = Field(ge=0)
    positions_checked: int = Field(ge=0)
    balances_checked: int = Field(ge=0)
    fills_checked: int = Field(ge=0)

    trading_gate_released: bool

    @model_validator(mode="after")
    def validate_reconciliation_result(self) -> Self:
        if self.completed_at <= self.started_at:
            msg = "completed_at must be after started_at"
            raise ValueError(msg)
        if self.status is ReconciliationStatus.HEALTHY and self.mismatches:
            msg = "healthy reconciliation cannot contain mismatches"
            raise ValueError(msg)
        if self.status is ReconciliationStatus.MISMATCH and not self.mismatches:
            msg = "mismatch reconciliation requires at least one mismatch"
            raise ValueError(msg)
        if self.status is not ReconciliationStatus.HEALTHY and self.trading_gate_released:
            msg = "non-healthy reconciliation cannot release the trading gate"
            raise ValueError(msg)
        return self


def _reject_duplicate_strings(values: Iterable[object], *, field_name: str) -> None:
    seen: set[str] = set()
    for value in values:
        text = str(value)
        if text in seen:
            msg = f"{field_name} must not contain duplicate identifiers"
            raise ValueError(msg)
        seen.add(text)
