"""Cash balance projection helpers for portfolio accounting journals."""

from __future__ import annotations

from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from decimal import Decimal

from pmrp.portfolio.errors import PortfolioProjectionError
from pmrp.portfolio.journal import ACCOUNT_CASH
from pmrp.schemas.identifiers import AccountId
from pmrp.schemas.numeric import Money, validate_currency
from pmrp.schemas.portfolio import AccountingJournalEntry, CashBalance
from pmrp.schemas.serialization import canonical_sha256

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


def apply_journal_to_cash_balance(
    balance: CashBalance,
    journal_entry: AccountingJournalEntry,
) -> CashBalanceProjectionResult:
    """Apply one journal entry's cash movement to an existing cash balance."""

    if journal_entry.occurred_at < balance.captured_at:
        msg = "journal entry occurred_at must not be before balance captured_at"
        raise PortfolioProjectionError(msg)

    cash_delta = _cash_delta_for_currency(journal_entry, balance.currency)
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


def _cash_delta_for_currency(
    journal_entry: AccountingJournalEntry,
    currency: str,
) -> Money:
    validated_currency = validate_currency(currency)
    matching_cash_lines = tuple(
        line
        for line in journal_entry.lines
        if line.account_code == ACCOUNT_CASH and line.currency == validated_currency
    )
    if not matching_cash_lines:
        msg = "journal entry does not contain a cash line for balance currency"
        raise PortfolioProjectionError(msg)

    return Money(
        amount=sum((line.amount for line in matching_cash_lines), start=_ZERO),
        currency=validated_currency,
    )
