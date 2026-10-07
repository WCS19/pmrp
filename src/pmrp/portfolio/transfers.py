"""Cash transfer accounting helpers for portfolio balances."""

from __future__ import annotations

from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Final

from pmrp.portfolio.balances import CashBalanceProjectionResult, apply_journal_to_cash_balance
from pmrp.portfolio.errors import PortfolioProjectionError
from pmrp.portfolio.journal import ACCOUNT_CASH
from pmrp.schemas.identifiers import EventId
from pmrp.schemas.numeric import Money, validate_currency
from pmrp.schemas.portfolio import AccountingJournalEntry, CashBalance, JournalLine
from pmrp.schemas.serialization import canonical_sha256

ACCOUNT_CASH_TRANSFER: Final = "cash_transfer"
TRANSFER_REFERENCE_TYPE: Final = "transfer"

_ZERO = Decimal("0")
_OUTBOUND_DIRECTION = "outbound"
_INBOUND_DIRECTION = "inbound"


@dataclass(frozen=True, slots=True)
class CashTransferJournalEntries:
    """Balanced journal entries for the two cash legs of a transfer."""

    outbound_journal_entry: AccountingJournalEntry
    inbound_journal_entry: AccountingJournalEntry


@dataclass(frozen=True, slots=True)
class CashTransferApplicationResult:
    """Result of idempotently applying one cash transfer."""

    from_balance: CashBalance
    to_balance: CashBalance
    outbound_projection: CashBalanceProjectionResult | None
    inbound_projection: CashBalanceProjectionResult | None
    outbound_journal_entry: AccountingJournalEntry | None
    inbound_journal_entry: AccountingJournalEntry | None
    applied_journal_entry_ids: frozenset[str]
    applied: bool
    duplicate_transfer: bool


def build_cash_transfer_journal_entries(
    *,
    from_balance: CashBalance,
    to_balance: CashBalance,
    amount: Money,
    transfer_id: str,
    source_event_id: EventId,
    occurred_at: datetime,
    created_at: datetime,
) -> CashTransferJournalEntries:
    """Build balanced outbound and inbound cash transfer journal entries."""

    _validate_transfer_inputs(
        from_balance=from_balance,
        to_balance=to_balance,
        amount=amount,
        transfer_id=transfer_id,
    )
    return CashTransferJournalEntries(
        outbound_journal_entry=_build_transfer_journal_entry(
            balance=from_balance,
            amount=amount,
            transfer_id=transfer_id,
            source_event_id=source_event_id,
            occurred_at=occurred_at,
            created_at=created_at,
            direction=_OUTBOUND_DIRECTION,
        ),
        inbound_journal_entry=_build_transfer_journal_entry(
            balance=to_balance,
            amount=amount,
            transfer_id=transfer_id,
            source_event_id=source_event_id,
            occurred_at=occurred_at,
            created_at=created_at,
            direction=_INBOUND_DIRECTION,
        ),
    )


def apply_cash_transfer_once(
    *,
    from_balance: CashBalance,
    to_balance: CashBalance,
    amount: Money,
    transfer_id: str,
    applied_journal_entry_ids: AbstractSet[str],
    source_event_id: EventId,
    occurred_at: datetime,
    created_at: datetime,
) -> CashTransferApplicationResult:
    """Apply a cash transfer once and no-op when both transfer journal legs exist."""

    _validate_transfer_inputs(
        from_balance=from_balance,
        to_balance=to_balance,
        amount=amount,
        transfer_id=transfer_id,
    )
    existing_journal_ids = frozenset(applied_journal_entry_ids)
    outbound_journal_entry_id = derive_cash_transfer_journal_entry_id(
        balance=from_balance,
        transfer_id=transfer_id,
        direction=_OUTBOUND_DIRECTION,
    )
    inbound_journal_entry_id = derive_cash_transfer_journal_entry_id(
        balance=to_balance,
        transfer_id=transfer_id,
        direction=_INBOUND_DIRECTION,
    )
    transfer_journal_ids = frozenset({outbound_journal_entry_id, inbound_journal_entry_id})
    applied_transfer_ids = existing_journal_ids & transfer_journal_ids
    if applied_transfer_ids:
        if applied_transfer_ids != transfer_journal_ids:
            msg = "cash transfer idempotency state is partially applied"
            raise PortfolioProjectionError(msg)
        return CashTransferApplicationResult(
            from_balance=from_balance,
            to_balance=to_balance,
            outbound_projection=None,
            inbound_projection=None,
            outbound_journal_entry=None,
            inbound_journal_entry=None,
            applied_journal_entry_ids=existing_journal_ids,
            applied=False,
            duplicate_transfer=True,
        )

    journal_entries = build_cash_transfer_journal_entries(
        from_balance=from_balance,
        to_balance=to_balance,
        amount=amount,
        transfer_id=transfer_id,
        source_event_id=source_event_id,
        occurred_at=occurred_at,
        created_at=created_at,
    )
    outbound_projection = apply_journal_to_cash_balance(
        from_balance,
        journal_entries.outbound_journal_entry,
    )
    inbound_projection = apply_journal_to_cash_balance(
        to_balance,
        journal_entries.inbound_journal_entry,
    )
    return CashTransferApplicationResult(
        from_balance=outbound_projection.balance,
        to_balance=inbound_projection.balance,
        outbound_projection=outbound_projection,
        inbound_projection=inbound_projection,
        outbound_journal_entry=journal_entries.outbound_journal_entry,
        inbound_journal_entry=journal_entries.inbound_journal_entry,
        applied_journal_entry_ids=existing_journal_ids | transfer_journal_ids,
        applied=True,
        duplicate_transfer=False,
    )


def derive_cash_transfer_journal_entry_id(
    *,
    balance: CashBalance,
    transfer_id: str,
    direction: str,
) -> str:
    """Derive a stable journal entry ID for one leg of a cash transfer."""

    _validate_transfer_id(transfer_id)
    _validate_transfer_direction(direction)
    digest = canonical_sha256(
        {
            "balance_id": balance.balance_id,
            "direction": direction,
            "schema": "pmrp.cash_transfer_journal_entry.v1",
            "transfer_id": transfer_id,
        }
    ).removeprefix("sha256:")
    return f"journal_cash_transfer_{digest[:32]}"


def _build_transfer_journal_entry(
    *,
    balance: CashBalance,
    amount: Money,
    transfer_id: str,
    source_event_id: EventId,
    occurred_at: datetime,
    created_at: datetime,
    direction: str,
) -> AccountingJournalEntry:
    _validate_transfer_direction(direction)
    cash_amount = amount.amount if direction == _INBOUND_DIRECTION else -amount.amount
    return AccountingJournalEntry(
        journal_entry_id=derive_cash_transfer_journal_entry_id(
            balance=balance,
            transfer_id=transfer_id,
            direction=direction,
        ),
        occurred_at=occurred_at,
        source_event_id=source_event_id,
        reference_type=TRANSFER_REFERENCE_TYPE,
        reference_id=transfer_id,
        lines=(
            JournalLine(
                account_code=ACCOUNT_CASH,
                amount=cash_amount,
                currency=amount.currency,
                description=f"Cash transfer {direction} cash movement.",
            ),
            JournalLine(
                account_code=ACCOUNT_CASH_TRANSFER,
                amount=-cash_amount,
                currency=amount.currency,
                description=f"Cash transfer {direction} offset.",
            ),
        ),
        description=f"Cash transfer {direction} accounting for {balance.balance_id}.",
        created_at=created_at,
    )


def _validate_transfer_inputs(
    *,
    from_balance: CashBalance,
    to_balance: CashBalance,
    amount: Money,
    transfer_id: str,
) -> None:
    _validate_transfer_id(transfer_id)
    if from_balance.balance_id == to_balance.balance_id:
        msg = "cash transfer requires distinct source and destination balances"
        raise PortfolioProjectionError(msg)
    if from_balance.currency != to_balance.currency:
        msg = "cash transfer balances must use the same currency"
        raise PortfolioProjectionError(msg)
    validated_currency = validate_currency(amount.currency)
    if from_balance.currency != validated_currency:
        msg = "cash transfer amount currency must match balance currency"
        raise PortfolioProjectionError(msg)
    if amount.amount <= _ZERO:
        msg = "cash transfer amount must be positive"
        raise PortfolioProjectionError(msg)


def _validate_transfer_id(transfer_id: str) -> None:
    if transfer_id == "" or transfer_id.strip() != transfer_id:
        msg = "cash transfer transfer_id is required without surrounding whitespace"
        raise PortfolioProjectionError(msg)


def _validate_transfer_direction(direction: str) -> None:
    if direction not in {_OUTBOUND_DIRECTION, _INBOUND_DIRECTION}:
        msg = "cash transfer direction must be inbound or outbound"
        raise PortfolioProjectionError(msg)
