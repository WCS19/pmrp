"""Settlement accounting helpers for portfolio positions."""

from __future__ import annotations

from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Final

from pmrp.portfolio.balances import CashBalanceProjectionResult, apply_journal_to_cash_balance
from pmrp.portfolio.errors import PortfolioProjectionError
from pmrp.portfolio.journal import (
    ACCOUNT_CASH,
    ACCOUNT_POSITION_COST,
    ACCOUNT_SETTLEMENT_PNL,
)
from pmrp.schemas.identifiers import EventId
from pmrp.schemas.numeric import Money, validate_currency
from pmrp.schemas.portfolio import (
    AccountingJournalEntry,
    CashBalance,
    JournalLine,
    Position,
    Settlement,
    SettlementStatus,
)
from pmrp.schemas.serialization import canonical_sha256

SETTLEMENT_REFERENCE_TYPE: Final = "settlement"

_ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class SettlementAccountingResult:
    """Settlement accounting amounts for one canonical position."""

    cash_delta: Money
    position_cost_basis: Money
    settlement_pnl: Money
    settled_quantity: Decimal
    winning_position: bool


@dataclass(frozen=True, slots=True)
class SettlementPositionProjectionResult:
    """Result of closing one canonical position through settlement."""

    position: Position
    settlement_accounting: SettlementAccountingResult


@dataclass(frozen=True, slots=True)
class SettlementApplicationResult:
    """Result of idempotently applying a settlement to position and cash projections."""

    position: Position
    cash_balance: CashBalance
    position_projection: SettlementPositionProjectionResult | None
    cash_projection: CashBalanceProjectionResult | None
    journal_entry: AccountingJournalEntry | None
    applied_journal_entry_ids: frozenset[str]
    applied: bool
    duplicate_settlement: bool


def build_settlement_accounting_result(
    *,
    position: Position,
    settlement: Settlement,
    currency: str,
) -> SettlementAccountingResult:
    """Calculate deterministic settlement amounts for one position."""

    validated_currency = validate_currency(currency)
    _validate_settlement_position(position, settlement, currency=validated_currency)

    assert settlement.payout_per_unit is not None
    assert position.average_entry_price is not None
    position_cost_basis = position.quantity * position.average_entry_price
    winning_position = position.outcome_id in settlement.winning_outcome_ids
    payout_per_unit = settlement.payout_per_unit if winning_position else _ZERO
    cash_delta = position.quantity * payout_per_unit
    settlement_pnl = cash_delta - position_cost_basis

    return SettlementAccountingResult(
        cash_delta=Money(amount=cash_delta, currency=validated_currency),
        position_cost_basis=Money(amount=position_cost_basis, currency=validated_currency),
        settlement_pnl=Money(amount=settlement_pnl, currency=validated_currency),
        settled_quantity=abs(position.quantity),
        winning_position=winning_position,
    )


def apply_settlement_to_position(
    *,
    position: Position,
    settlement: Settlement,
    currency: str,
) -> SettlementPositionProjectionResult:
    """Close one position through a settled market outcome."""

    validated_currency = validate_currency(currency)
    _validate_settlement_position(position, settlement, currency=validated_currency)
    assert settlement.settled_at is not None
    if settlement.settled_at < position.last_updated_at:
        msg = "settlement settled_at is older than the position update horizon"
        raise PortfolioProjectionError(msg)

    accounting = build_settlement_accounting_result(
        position=position,
        settlement=settlement,
        currency=validated_currency,
    )
    projected_position = Position(
        position_id=position.position_id,
        exchange=position.exchange,
        account_id=position.account_id,
        market_id=position.market_id,
        contract_id=position.contract_id,
        outcome_id=position.outcome_id,
        quantity=_ZERO,
        average_entry_price=None,
        realized_pnl=Money(
            amount=position.realized_pnl.amount + accounting.settlement_pnl.amount,
            currency=validated_currency,
        ),
        unrealized_pnl=Money(amount=_ZERO, currency=validated_currency),
        fees_paid=position.fees_paid,
        rebates_received=position.rebates_received,
        opened_at=None,
        last_updated_at=settlement.settled_at,
        aggregate_version=position.aggregate_version + 1,
    )
    return SettlementPositionProjectionResult(
        position=projected_position,
        settlement_accounting=accounting,
    )


def apply_settlement_once(
    *,
    position: Position,
    cash_balance: CashBalance,
    settlement: Settlement,
    applied_journal_entry_ids: AbstractSet[str],
    currency: str,
    source_event_id: EventId,
    created_at: datetime,
) -> SettlementApplicationResult:
    """Apply a settlement once and return a no-op result for duplicates."""

    validated_currency = validate_currency(currency)
    _validate_cash_balance_for_position(
        cash_balance,
        position,
        currency=validated_currency,
    )
    existing_journal_ids = frozenset(applied_journal_entry_ids)
    journal_entry_id = derive_settlement_journal_entry_id(position, settlement)
    if journal_entry_id in existing_journal_ids:
        return SettlementApplicationResult(
            position=position,
            cash_balance=cash_balance,
            position_projection=None,
            cash_projection=None,
            journal_entry=None,
            applied_journal_entry_ids=existing_journal_ids,
            applied=False,
            duplicate_settlement=True,
        )

    position_projection = apply_settlement_to_position(
        position=position,
        settlement=settlement,
        currency=validated_currency,
    )
    journal_entry = build_settlement_journal_entry(
        position=position,
        settlement=settlement,
        currency=validated_currency,
        source_event_id=source_event_id,
        created_at=created_at,
    )
    cash_projection = apply_journal_to_cash_balance(cash_balance, journal_entry)

    return SettlementApplicationResult(
        position=position_projection.position,
        cash_balance=cash_projection.balance,
        position_projection=position_projection,
        cash_projection=cash_projection,
        journal_entry=journal_entry,
        applied_journal_entry_ids=existing_journal_ids | {journal_entry_id},
        applied=True,
        duplicate_settlement=False,
    )


def build_settlement_journal_entry(
    *,
    position: Position,
    settlement: Settlement,
    currency: str,
    source_event_id: EventId,
    created_at: datetime,
) -> AccountingJournalEntry:
    """Build a balanced accounting journal entry for one settled position."""

    result = build_settlement_accounting_result(
        position=position,
        settlement=settlement,
        currency=currency,
    )
    assert settlement.settled_at is not None

    return AccountingJournalEntry(
        journal_entry_id=derive_settlement_journal_entry_id(position, settlement),
        occurred_at=settlement.settled_at,
        source_event_id=source_event_id,
        reference_type=SETTLEMENT_REFERENCE_TYPE,
        reference_id=settlement.settlement_id,
        lines=(
            JournalLine(
                account_code=ACCOUNT_CASH,
                amount=result.cash_delta.amount,
                currency=result.cash_delta.currency,
                description="Settlement cash movement.",
            ),
            JournalLine(
                account_code=ACCOUNT_POSITION_COST,
                amount=-result.position_cost_basis.amount,
                currency=result.position_cost_basis.currency,
                description="Settlement clears position cost basis.",
            ),
            JournalLine(
                account_code=ACCOUNT_SETTLEMENT_PNL,
                amount=-result.settlement_pnl.amount,
                currency=result.settlement_pnl.currency,
                description="Settlement PnL offset.",
            ),
        ),
        description=f"Settlement accounting for {position.position_id}.",
        created_at=created_at,
    )


def derive_settlement_journal_entry_id(position: Position, settlement: Settlement) -> str:
    """Derive a stable journal entry identifier for one position settlement."""

    digest = canonical_sha256(
        {
            "position_id": position.position_id,
            "schema": "pmrp.settlement_journal_entry.v1",
            "settlement_id": settlement.settlement_id,
        }
    ).removeprefix("sha256:")
    return f"journal_settlement_{digest[:32]}"


def _validate_settlement_position(
    position: Position,
    settlement: Settlement,
    *,
    currency: str,
) -> None:
    if settlement.status is not SettlementStatus.SETTLED:
        msg = "settlement accounting requires settled settlement status"
        raise PortfolioProjectionError(msg)
    if settlement.settled_at is None:
        msg = "settlement accounting requires settled_at"
        raise PortfolioProjectionError(msg)
    if settlement.payout_per_unit is None:
        msg = "settlement accounting requires payout_per_unit"
        raise PortfolioProjectionError(msg)
    if position.exchange != settlement.exchange:
        msg = "position exchange does not match settlement exchange"
        raise PortfolioProjectionError(msg)
    if position.market_id != settlement.market_id:
        msg = "position market_id does not match settlement market_id"
        raise PortfolioProjectionError(msg)
    if position.quantity == _ZERO:
        msg = "settlement accounting requires nonzero position quantity"
        raise PortfolioProjectionError(msg)
    if position.average_entry_price is None:
        msg = "settlement accounting requires position average_entry_price"
        raise PortfolioProjectionError(msg)
    _validate_money(position.realized_pnl, currency=currency, field_name="realized_pnl")
    _validate_money(position.unrealized_pnl, currency=currency, field_name="unrealized_pnl")
    _validate_money(position.fees_paid, currency=currency, field_name="fees_paid")
    _validate_money(position.rebates_received, currency=currency, field_name="rebates_received")


def _validate_money(money: Money, *, currency: str, field_name: str) -> None:
    if money.currency != currency:
        msg = f"{field_name} currency must match settlement currency"
        raise PortfolioProjectionError(msg)


def _validate_cash_balance_for_position(
    cash_balance: CashBalance,
    position: Position,
    *,
    currency: str,
) -> None:
    if cash_balance.exchange != position.exchange:
        msg = "cash balance exchange does not match position exchange"
        raise PortfolioProjectionError(msg)
    if cash_balance.account_id != position.account_id:
        msg = "cash balance account_id does not match position account_id"
        raise PortfolioProjectionError(msg)
    if cash_balance.currency != currency:
        msg = "cash balance currency must match settlement currency"
        raise PortfolioProjectionError(msg)
