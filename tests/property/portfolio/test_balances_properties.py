"""Property tests for cash balance projection invariants."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from pmrp.portfolio import (
    ACCOUNT_BALANCE_CORRECTION,
    ACCOUNT_CASH,
    apply_balance_correction_once,
    apply_journal_to_cash_balance_once,
    build_balance_correction_journal_entry,
)
from pmrp.schemas.identifiers import EventId
from pmrp.schemas.portfolio import AccountingJournalEntry, CashBalance, JournalLine

pytestmark = pytest.mark.property

CAPTURED_AT = datetime(2026, 9, 25, 13, 59, tzinfo=UTC)
OCCURRED_AT = datetime(2026, 9, 25, 14, 0, tzinfo=UTC)
CREATED_AT = datetime(2026, 9, 25, 14, 0, 1, tzinfo=UTC)

_MONEY_AMOUNTS = st.integers(min_value=-1_000_000, max_value=1_000_000).map(
    lambda cents: Decimal(cents) / Decimal("100")
)


@given(
    available=_MONEY_AMOUNTS,
    reserved=st.integers(min_value=0, max_value=1_000_000).map(
        lambda cents: Decimal(cents) / Decimal("100")
    ),
    cash_delta=_MONEY_AMOUNTS,
)
def test_apply_journal_to_cash_balance_preserves_balance_identity(
    available: Decimal,
    reserved: Decimal,
    cash_delta: Decimal,
) -> None:
    balance = _balance(available=available, reserved=reserved)
    journal = _journal(cash_delta)

    result = apply_journal_to_cash_balance_once(
        balance=balance,
        journal_entry=journal,
        applied_journal_entry_ids=frozenset(),
    )

    assert result.applied is True
    assert result.balance.available == available + cash_delta
    assert result.balance.reserved == reserved
    assert result.balance.total == result.balance.available + result.balance.reserved
    assert result.applied_journal_entry_ids == frozenset({journal.journal_entry_id})


@given(cash_delta=_MONEY_AMOUNTS)
def test_apply_journal_to_cash_balance_duplicate_is_noop(cash_delta: Decimal) -> None:
    balance = _balance(available=Decimal("100"), reserved=Decimal("0"))
    journal = _journal(cash_delta)

    first = apply_journal_to_cash_balance_once(
        balance=balance,
        journal_entry=journal,
        applied_journal_entry_ids=frozenset(),
    )
    duplicate = apply_journal_to_cash_balance_once(
        balance=first.balance,
        journal_entry=journal,
        applied_journal_entry_ids=first.applied_journal_entry_ids,
    )

    assert duplicate.applied is False
    assert duplicate.duplicate_journal_entry is True
    assert duplicate.balance == first.balance
    assert duplicate.cash_projection is None
    assert duplicate.applied_journal_entry_ids == first.applied_journal_entry_ids


@given(
    available=_MONEY_AMOUNTS,
    observed_available=_MONEY_AMOUNTS,
    reserved=st.integers(min_value=0, max_value=1_000_000).map(
        lambda cents: Decimal(cents) / Decimal("100")
    ),
)
def test_apply_balance_correction_once_projects_observed_balance(
    available: Decimal,
    observed_available: Decimal,
    reserved: Decimal,
) -> None:
    assume(available != observed_available)
    balance = _balance(available=available, reserved=reserved)
    observed = _balance(
        available=observed_available,
        reserved=reserved,
        captured_at=OCCURRED_AT,
    )

    result = apply_balance_correction_once(
        balance=balance,
        observed_balance=observed,
        applied_journal_entry_ids=frozenset(),
        reference_id="recon_property_balance_correction",
        source_event_id=EventId("evt_property_balance_correction"),
        created_at=CREATED_AT,
    )

    assert result.applied is True
    assert result.balance == observed
    assert result.cash_projection is not None
    assert result.journal_entry is not None
    assert result.cash_projection.cash_delta.amount == observed_available - available
    assert result.applied_journal_entry_ids == frozenset({result.journal_entry.journal_entry_id})


@given(
    available=_MONEY_AMOUNTS,
    observed_available=_MONEY_AMOUNTS,
    reserved=st.integers(min_value=0, max_value=1_000_000).map(
        lambda cents: Decimal(cents) / Decimal("100")
    ),
)
def test_balance_correction_journal_entries_balance(
    available: Decimal,
    observed_available: Decimal,
    reserved: Decimal,
) -> None:
    assume(available != observed_available)
    balance = _balance(available=available, reserved=reserved)
    observed = _balance(
        available=observed_available,
        reserved=reserved,
        captured_at=OCCURRED_AT,
    )

    journal = build_balance_correction_journal_entry(
        balance=balance,
        observed_balance=observed,
        reference_id="recon_property_balance_correction",
        source_event_id=EventId("evt_property_balance_correction_journal"),
        created_at=CREATED_AT,
    )

    assert sum((line.amount for line in journal.lines), start=Decimal("0")) == Decimal("0")
    assert tuple(line.account_code for line in journal.lines) == (
        ACCOUNT_CASH,
        ACCOUNT_BALANCE_CORRECTION,
    )


def _balance(
    *,
    available: Decimal,
    reserved: Decimal,
    captured_at: datetime = CAPTURED_AT,
) -> CashBalance:
    return CashBalance(
        balance_id="cash_property_balance_001",
        exchange="kalshi",
        account_id="acct_property_balance",
        currency="USD",
        available=available,
        reserved=reserved,
        total=available + reserved,
        captured_at=captured_at,
    )


def _journal(cash_delta: Decimal) -> AccountingJournalEntry:
    return AccountingJournalEntry(
        journal_entry_id="journal_property_balance_001",
        occurred_at=OCCURRED_AT,
        source_event_id=EventId("evt_property_balance_journal"),
        reference_type="fill",
        reference_id="fill_property_balance",
        lines=(
            JournalLine(
                account_code=ACCOUNT_CASH,
                amount=cash_delta,
                currency="USD",
                description="cash movement",
            ),
            JournalLine(
                account_code="balance_offset",
                amount=-cash_delta,
                currency="USD",
                description="offset",
            ),
        ),
        description="Property cash balance projection journal.",
        created_at=CREATED_AT,
    )
