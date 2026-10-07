"""Cash balance projection helpers for portfolio accounting journals."""

from __future__ import annotations

from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Final

from pmrp.portfolio.errors import PortfolioProjectionError
from pmrp.portfolio.journal import ACCOUNT_CASH
from pmrp.schemas.identifiers import AccountId, EventId
from pmrp.schemas.numeric import Money, validate_currency
from pmrp.schemas.portfolio import AccountingJournalEntry, CashBalance, JournalLine
from pmrp.schemas.serialization import canonical_sha256

ACCOUNT_BALANCE_CORRECTION: Final = "balance_correction"
BALANCE_CORRECTION_REFERENCE_TYPE: Final = "balance_correction"

_ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class CashBalanceProjectionResult:
    """Result of applying one accounting journal entry to one cash balance."""

    balance: CashBalance
    cash_delta: Money


@dataclass(frozen=True, slots=True)
class CashBalanceApplicationResult:
    """Result of idempotently applying a journal entry to a cash balance."""

    balance: CashBalance
    cash_projection: CashBalanceProjectionResult | None
    applied_journal_entry_ids: frozenset[str]
    applied: bool
    duplicate_journal_entry: bool


@dataclass(frozen=True, slots=True)
class CashBalanceCorrectionResult:
    """Result of idempotently applying an observed cash balance correction."""

    balance: CashBalance
    cash_projection: CashBalanceProjectionResult | None
    journal_entry: AccountingJournalEntry | None
    applied_journal_entry_ids: frozenset[str]
    applied: bool
    duplicate_correction: bool


def apply_journal_to_cash_balance(
    balance: CashBalance,
    journal_entry: AccountingJournalEntry,
    *,
    cash_account_code: str = ACCOUNT_CASH,
) -> CashBalanceProjectionResult:
    """Apply one journal entry's cash movement to an existing cash balance."""

    if journal_entry.occurred_at < balance.captured_at:
        msg = "journal entry occurred_at must not be before balance captured_at"
        raise PortfolioProjectionError(msg)

    cash_delta = _cash_delta_for_currency(
        journal_entry,
        balance.currency,
        cash_account_code=cash_account_code,
    )
    projected_balance = CashBalance(
        balance_id=balance.balance_id,
        exchange=balance.exchange,
        account_id=balance.account_id,
        currency=balance.currency,
        available=balance.available + cash_delta.amount,
        reserved=balance.reserved,
        total=balance.total + cash_delta.amount,
        captured_at=journal_entry.occurred_at,
    )
    return CashBalanceProjectionResult(
        balance=projected_balance,
        cash_delta=cash_delta,
    )


def apply_journal_to_cash_balance_once(
    *,
    balance: CashBalance,
    journal_entry: AccountingJournalEntry,
    applied_journal_entry_ids: AbstractSet[str],
) -> CashBalanceApplicationResult:
    """Apply a journal entry once and return a no-op result for duplicates."""

    existing_journal_ids = frozenset(applied_journal_entry_ids)
    if journal_entry.journal_entry_id in existing_journal_ids:
        return CashBalanceApplicationResult(
            balance=balance,
            cash_projection=None,
            applied_journal_entry_ids=existing_journal_ids,
            applied=False,
            duplicate_journal_entry=True,
        )

    projection = apply_journal_to_cash_balance(balance, journal_entry)
    return CashBalanceApplicationResult(
        balance=projection.balance,
        cash_projection=projection,
        applied_journal_entry_ids=existing_journal_ids | {journal_entry.journal_entry_id},
        applied=True,
        duplicate_journal_entry=False,
    )


def build_balance_correction_journal_entry(
    *,
    balance: CashBalance,
    observed_balance: CashBalance,
    reference_id: str,
    source_event_id: EventId,
    created_at: datetime,
) -> AccountingJournalEntry:
    """Build a balanced journal entry that corrects available cash to observation."""

    _validate_balance_correction_application(
        balance=balance,
        observed_balance=observed_balance,
        reference_id=reference_id,
    )
    cash_delta = observed_balance.available - balance.available
    if cash_delta == _ZERO:
        msg = "balance correction requires nonzero cash delta"
        raise PortfolioProjectionError(msg)

    return AccountingJournalEntry(
        journal_entry_id=derive_balance_correction_journal_entry_id(
            balance=balance,
            observed_balance=observed_balance,
            reference_id=reference_id,
        ),
        occurred_at=observed_balance.captured_at,
        source_event_id=source_event_id,
        reference_type=BALANCE_CORRECTION_REFERENCE_TYPE,
        reference_id=reference_id,
        lines=(
            JournalLine(
                account_code=ACCOUNT_CASH,
                amount=cash_delta,
                currency=balance.currency,
                description="Balance correction cash movement.",
            ),
            JournalLine(
                account_code=ACCOUNT_BALANCE_CORRECTION,
                amount=-cash_delta,
                currency=balance.currency,
                description="Balance correction offset.",
            ),
        ),
        description=f"Cash balance correction for {balance.balance_id}.",
        created_at=created_at,
    )


def apply_balance_correction_once(
    *,
    balance: CashBalance,
    observed_balance: CashBalance,
    applied_journal_entry_ids: AbstractSet[str],
    reference_id: str,
    source_event_id: EventId,
    created_at: datetime,
) -> CashBalanceCorrectionResult:
    """Apply an observed cash balance correction once."""

    _validate_balance_correction_identity(
        balance=balance,
        observed_balance=observed_balance,
        reference_id=reference_id,
    )
    existing_journal_ids = frozenset(applied_journal_entry_ids)
    journal_entry_id = derive_balance_correction_journal_entry_id(
        balance=balance,
        observed_balance=observed_balance,
        reference_id=reference_id,
    )
    if journal_entry_id in existing_journal_ids:
        return CashBalanceCorrectionResult(
            balance=balance,
            cash_projection=None,
            journal_entry=None,
            applied_journal_entry_ids=existing_journal_ids,
            applied=False,
            duplicate_correction=True,
        )

    journal_entry = build_balance_correction_journal_entry(
        balance=balance,
        observed_balance=observed_balance,
        reference_id=reference_id,
        source_event_id=source_event_id,
        created_at=created_at,
    )
    projection = apply_journal_to_cash_balance(balance, journal_entry)
    return CashBalanceCorrectionResult(
        balance=projection.balance,
        cash_projection=projection,
        journal_entry=journal_entry,
        applied_journal_entry_ids=existing_journal_ids | {journal_entry_id},
        applied=True,
        duplicate_correction=False,
    )


def derive_cash_balance_id(*, exchange: str, account_id: AccountId, currency: str) -> str:
    """Derive a stable cash balance identifier from exchange account currency identity."""

    validated_currency = validate_currency(currency)
    digest = canonical_sha256(
        {
            "account_id": account_id,
            "currency": validated_currency,
            "exchange": exchange,
            "schema": "pmrp.cash_balance_identity.v1",
        }
    ).removeprefix("sha256:")
    return f"cash_{digest[:32]}"


def derive_balance_correction_journal_entry_id(
    *,
    balance: CashBalance,
    observed_balance: CashBalance,
    reference_id: str,
) -> str:
    """Derive a stable journal entry identifier for an observed balance correction."""

    digest = canonical_sha256(
        {
            "balance_id": balance.balance_id,
            "observed_available": observed_balance.available,
            "observed_captured_at": observed_balance.captured_at,
            "observed_total": observed_balance.total,
            "reference_id": reference_id,
            "schema": "pmrp.balance_correction_journal_entry.v1",
        }
    ).removeprefix("sha256:")
    return f"journal_balance_correction_{digest[:32]}"


def _cash_delta_for_currency(
    journal_entry: AccountingJournalEntry,
    currency: str,
    *,
    cash_account_code: str,
) -> Money:
    validated_currency = validate_currency(currency)
    if cash_account_code == "" or cash_account_code.strip() != cash_account_code:
        msg = "cash account code is required without surrounding whitespace"
        raise PortfolioProjectionError(msg)
    matching_cash_lines = tuple(
        line
        for line in journal_entry.lines
        if line.account_code == cash_account_code and line.currency == validated_currency
    )
    if not matching_cash_lines:
        msg = "journal entry does not contain a cash line for balance currency"
        raise PortfolioProjectionError(msg)

    return Money(
        amount=sum((line.amount for line in matching_cash_lines), start=_ZERO),
        currency=validated_currency,
    )


def _validate_balance_correction_identity(
    *,
    balance: CashBalance,
    observed_balance: CashBalance,
    reference_id: str,
) -> None:
    if not reference_id:
        msg = "balance correction reference_id is required"
        raise PortfolioProjectionError(msg)
    if observed_balance.balance_id != balance.balance_id:
        msg = "observed balance_id does not match balance"
        raise PortfolioProjectionError(msg)
    if observed_balance.exchange != balance.exchange:
        msg = "observed exchange does not match balance exchange"
        raise PortfolioProjectionError(msg)
    if observed_balance.account_id != balance.account_id:
        msg = "observed account_id does not match balance account_id"
        raise PortfolioProjectionError(msg)
    if observed_balance.currency != balance.currency:
        msg = "observed currency does not match balance currency"
        raise PortfolioProjectionError(msg)


def _validate_balance_correction_application(
    *,
    balance: CashBalance,
    observed_balance: CashBalance,
    reference_id: str,
) -> None:
    _validate_balance_correction_identity(
        balance=balance,
        observed_balance=observed_balance,
        reference_id=reference_id,
    )
    if observed_balance.captured_at < balance.captured_at:
        msg = "observed balance captured_at must not be before balance captured_at"
        raise PortfolioProjectionError(msg)
    if observed_balance.reserved != balance.reserved:
        msg = "balance correction cannot change reserved cash"
        raise PortfolioProjectionError(msg)
