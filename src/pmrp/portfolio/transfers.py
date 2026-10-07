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
_MAX_ACCOUNT_CODE_LENGTH = 128


@dataclass(frozen=True, slots=True)
class CashTransferApplicationResult:
    """Result of idempotently applying one cash transfer."""

    from_balance: CashBalance
    to_balance: CashBalance
    outbound_projection: CashBalanceProjectionResult | None
    inbound_projection: CashBalanceProjectionResult | None
    journal_entry: AccountingJournalEntry | None
    applied_journal_entry_ids: frozenset[str]
    applied: bool
    duplicate_transfer: bool


def build_cash_transfer_journal_entry(
    *,
    from_balance: CashBalance,
    to_balance: CashBalance,
    amount: Money,
    transfer_id: str,
    source_event_id: EventId,
    occurred_at: datetime,
    created_at: datetime,
) -> AccountingJournalEntry:
    """Build one balanced cash transfer journal entry.

    The source event maps to one journal header so persisted journal entries
    remain compatible with the unique source_event_id constraint. Balance
    identity is encoded in cash account codes for the two cash lines.
    """

    _validate_transfer_inputs(
        from_balance=from_balance,
        to_balance=to_balance,
        amount=amount,
        transfer_id=transfer_id,
    )
    return AccountingJournalEntry(
        journal_entry_id=derive_cash_transfer_journal_entry_id(transfer_id=transfer_id),
        occurred_at=occurred_at,
        source_event_id=source_event_id,
        reference_type=TRANSFER_REFERENCE_TYPE,
        reference_id=transfer_id,
        lines=(
            JournalLine(
                account_code=_cash_balance_account_code(from_balance),
                amount=-amount.amount,
                currency=amount.currency,
                description="Cash transfer outbound cash movement.",
            ),
            JournalLine(
                account_code=ACCOUNT_CASH_TRANSFER,
                amount=amount.amount,
                currency=amount.currency,
                description="Cash transfer outbound offset.",
            ),
            JournalLine(
                account_code=_cash_balance_account_code(to_balance),
                amount=amount.amount,
                currency=amount.currency,
                description="Cash transfer inbound cash movement.",
            ),
            JournalLine(
                account_code=ACCOUNT_CASH_TRANSFER,
                amount=-amount.amount,
                currency=amount.currency,
                description="Cash transfer inbound offset.",
            ),
        ),
        description=f"Cash transfer accounting for {transfer_id}.",
        created_at=created_at,
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
    """Apply a cash transfer once and no-op when its journal entry already exists."""

    _validate_transfer_inputs(
        from_balance=from_balance,
        to_balance=to_balance,
        amount=amount,
        transfer_id=transfer_id,
    )
    existing_journal_ids = frozenset(applied_journal_entry_ids)
    journal_entry_id = derive_cash_transfer_journal_entry_id(transfer_id=transfer_id)
    if journal_entry_id in existing_journal_ids:
        return CashTransferApplicationResult(
            from_balance=from_balance,
            to_balance=to_balance,
            outbound_projection=None,
            inbound_projection=None,
            journal_entry=None,
            applied_journal_entry_ids=existing_journal_ids,
            applied=False,
            duplicate_transfer=True,
        )

    journal_entry = build_cash_transfer_journal_entry(
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
        journal_entry,
        cash_account_code=_cash_balance_account_code(from_balance),
    )
    inbound_projection = apply_journal_to_cash_balance(
        to_balance,
        journal_entry,
        cash_account_code=_cash_balance_account_code(to_balance),
    )
    return CashTransferApplicationResult(
        from_balance=outbound_projection.balance,
        to_balance=inbound_projection.balance,
        outbound_projection=outbound_projection,
        inbound_projection=inbound_projection,
        journal_entry=journal_entry,
        applied_journal_entry_ids=existing_journal_ids | {journal_entry_id},
        applied=True,
        duplicate_transfer=False,
    )


def derive_cash_transfer_journal_entry_id(*, transfer_id: str) -> str:
    """Derive a stable journal entry ID for a cash transfer."""

    _validate_transfer_id(transfer_id)
    digest = canonical_sha256(
        {
            "schema": "pmrp.cash_transfer_journal_entry.v1",
            "transfer_id": transfer_id,
        }
    ).removeprefix("sha256:")
    return f"journal_cash_transfer_{digest[:32]}"


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
    _cash_balance_account_code(from_balance)
    _cash_balance_account_code(to_balance)


def _validate_transfer_id(transfer_id: str) -> None:
    if transfer_id == "" or transfer_id.strip() != transfer_id:
        msg = "cash transfer transfer_id is required without surrounding whitespace"
        raise PortfolioProjectionError(msg)


def _cash_balance_account_code(balance: CashBalance) -> str:
    account_code = f"{ACCOUNT_CASH}:{balance.balance_id}"
    if len(account_code) > _MAX_ACCOUNT_CODE_LENGTH:
        msg = "cash transfer balance_id is too long for a cash account code"
        raise PortfolioProjectionError(msg)
    return account_code
