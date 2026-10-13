"""Standalone fee and rebate accounting helpers for portfolio balances."""

from __future__ import annotations

from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Final

from pmrp.portfolio.balances import CashBalanceProjectionResult, apply_journal_to_cash_balance
from pmrp.portfolio.errors import PortfolioProjectionError
from pmrp.portfolio.journal import ACCOUNT_CASH, ACCOUNT_FEES_PAID, ACCOUNT_REBATES_RECEIVED
from pmrp.schemas.identifiers import EventId
from pmrp.schemas.numeric import Money
from pmrp.schemas.portfolio import AccountingJournalEntry, CashBalance, JournalLine
from pmrp.schemas.serialization import canonical_sha256

FEE_REFERENCE_TYPE: Final = "fee"
REBATE_REFERENCE_TYPE: Final = "rebate"

_ZERO = Decimal("0")
_MAX_REFERENCE_ID_LENGTH = 128


@dataclass(frozen=True, slots=True)
class FeeApplicationResult:
    """Result of idempotently applying one standalone fee."""

    balance: CashBalance
    cash_projection: CashBalanceProjectionResult | None
    journal_entry: AccountingJournalEntry | None
    applied_journal_entry_ids: frozenset[str]
    applied: bool
    duplicate_fee: bool


@dataclass(frozen=True, slots=True)
class RebateApplicationResult:
    """Result of idempotently applying one standalone rebate."""

    balance: CashBalance
    cash_projection: CashBalanceProjectionResult | None
    journal_entry: AccountingJournalEntry | None
    applied_journal_entry_ids: frozenset[str]
    applied: bool
    duplicate_rebate: bool


def build_fee_journal_entry(
    *,
    amount: Money,
    fee_id: str,
    source_event_id: EventId,
    occurred_at: datetime,
    created_at: datetime,
) -> AccountingJournalEntry:
    """Build a balanced journal entry for an exchange-reported fee."""

    validated_fee_id = _validate_reference_id(fee_id, field_name="fee_id")
    _validate_positive_money(amount, field_name="fee")
    return AccountingJournalEntry(
        journal_entry_id=derive_fee_journal_entry_id(fee_id=validated_fee_id),
        occurred_at=occurred_at,
        source_event_id=source_event_id,
        reference_type=FEE_REFERENCE_TYPE,
        reference_id=validated_fee_id,
        lines=(
            JournalLine(
                account_code=ACCOUNT_CASH,
                amount=-amount.amount,
                currency=amount.currency,
                description="Fee cash movement.",
            ),
            JournalLine(
                account_code=ACCOUNT_FEES_PAID,
                amount=amount.amount,
                currency=amount.currency,
                description="Fee expense.",
            ),
        ),
        description=f"Fee accounting for {validated_fee_id}.",
        created_at=created_at,
    )


def build_rebate_journal_entry(
    *,
    amount: Money,
    rebate_id: str,
    source_event_id: EventId,
    occurred_at: datetime,
    created_at: datetime,
) -> AccountingJournalEntry:
    """Build a balanced journal entry for an exchange-reported rebate."""

    validated_rebate_id = _validate_reference_id(rebate_id, field_name="rebate_id")
    _validate_positive_money(amount, field_name="rebate")
    return AccountingJournalEntry(
        journal_entry_id=derive_rebate_journal_entry_id(rebate_id=validated_rebate_id),
        occurred_at=occurred_at,
        source_event_id=source_event_id,
        reference_type=REBATE_REFERENCE_TYPE,
        reference_id=validated_rebate_id,
        lines=(
            JournalLine(
                account_code=ACCOUNT_CASH,
                amount=amount.amount,
                currency=amount.currency,
                description="Rebate cash movement.",
            ),
            JournalLine(
                account_code=ACCOUNT_REBATES_RECEIVED,
                amount=-amount.amount,
                currency=amount.currency,
                description="Rebate income.",
            ),
        ),
        description=f"Rebate accounting for {validated_rebate_id}.",
        created_at=created_at,
    )


def apply_fee_once(
    *,
    balance: CashBalance,
    amount: Money,
    fee_id: str,
    applied_journal_entry_ids: AbstractSet[str],
    source_event_id: EventId,
    occurred_at: datetime,
    created_at: datetime,
) -> FeeApplicationResult:
    """Apply a standalone fee once and no-op for duplicate fee journal IDs."""

    _validate_balance_currency(balance, amount, field_name="fee")
    journal_entry_id = derive_fee_journal_entry_id(fee_id=fee_id)
    existing_journal_ids = frozenset(applied_journal_entry_ids)
    if journal_entry_id in existing_journal_ids:
        return FeeApplicationResult(
            balance=balance,
            cash_projection=None,
            journal_entry=None,
            applied_journal_entry_ids=existing_journal_ids,
            applied=False,
            duplicate_fee=True,
        )

    journal_entry = build_fee_journal_entry(
        amount=amount,
        fee_id=fee_id,
        source_event_id=source_event_id,
        occurred_at=occurred_at,
        created_at=created_at,
    )
    projection = apply_journal_to_cash_balance(balance, journal_entry)
    return FeeApplicationResult(
        balance=projection.balance,
        cash_projection=projection,
        journal_entry=journal_entry,
        applied_journal_entry_ids=existing_journal_ids | {journal_entry_id},
        applied=True,
        duplicate_fee=False,
    )


def apply_rebate_once(
    *,
    balance: CashBalance,
    amount: Money,
    rebate_id: str,
    applied_journal_entry_ids: AbstractSet[str],
    source_event_id: EventId,
    occurred_at: datetime,
    created_at: datetime,
) -> RebateApplicationResult:
    """Apply a standalone rebate once and no-op for duplicate rebate journal IDs."""

    _validate_balance_currency(balance, amount, field_name="rebate")
    journal_entry_id = derive_rebate_journal_entry_id(rebate_id=rebate_id)
    existing_journal_ids = frozenset(applied_journal_entry_ids)
    if journal_entry_id in existing_journal_ids:
        return RebateApplicationResult(
            balance=balance,
            cash_projection=None,
            journal_entry=None,
            applied_journal_entry_ids=existing_journal_ids,
            applied=False,
            duplicate_rebate=True,
        )

    journal_entry = build_rebate_journal_entry(
        amount=amount,
        rebate_id=rebate_id,
        source_event_id=source_event_id,
        occurred_at=occurred_at,
        created_at=created_at,
    )
    projection = apply_journal_to_cash_balance(balance, journal_entry)
    return RebateApplicationResult(
        balance=projection.balance,
        cash_projection=projection,
        journal_entry=journal_entry,
        applied_journal_entry_ids=existing_journal_ids | {journal_entry_id},
        applied=True,
        duplicate_rebate=False,
    )


def derive_fee_journal_entry_id(*, fee_id: str) -> str:
    """Derive a stable journal entry ID for a standalone fee."""

    validated_fee_id = _validate_reference_id(fee_id, field_name="fee_id")
    digest = canonical_sha256(
        {
            "fee_id": validated_fee_id,
            "schema": "pmrp.fee_journal_entry.v1",
        }
    ).removeprefix("sha256:")
    return f"journal_fee_{digest[:32]}"


def derive_rebate_journal_entry_id(*, rebate_id: str) -> str:
    """Derive a stable journal entry ID for a standalone rebate."""

    validated_rebate_id = _validate_reference_id(rebate_id, field_name="rebate_id")
    digest = canonical_sha256(
        {
            "rebate_id": validated_rebate_id,
            "schema": "pmrp.rebate_journal_entry.v1",
        }
    ).removeprefix("sha256:")
    return f"journal_rebate_{digest[:32]}"


def _validate_balance_currency(balance: CashBalance, amount: Money, *, field_name: str) -> None:
    if balance.currency != amount.currency:
        msg = f"{field_name} currency must match balance currency"
        raise PortfolioProjectionError(msg)


def _validate_positive_money(amount: Money, *, field_name: str) -> None:
    if amount.amount <= _ZERO:
        msg = f"{field_name} amount must be positive"
        raise PortfolioProjectionError(msg)


def _validate_reference_id(value: str, *, field_name: str) -> str:
    if value == "" or value.strip() != value:
        msg = f"{field_name} is required without surrounding whitespace"
        raise PortfolioProjectionError(msg)
    if len(value) > _MAX_REFERENCE_ID_LENGTH:
        msg = f"{field_name} must be at most {_MAX_REFERENCE_ID_LENGTH} characters"
        raise PortfolioProjectionError(msg)
    return value
