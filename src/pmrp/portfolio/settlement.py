"""Settlement accounting helpers for portfolio positions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Final

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


def build_settlement_accounting_result(
    *,
    position: Position,
    settlement: Settlement,
    currency: str,
) -> SettlementAccountingResult:
    """Calculate deterministic settlement amounts for one position."""

    validated_currency = validate_currency(currency)
    _validate_settlement_position(position, settlement)

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


def _validate_settlement_position(position: Position, settlement: Settlement) -> None:
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
