"""Property tests for standalone fee and rebate accounting invariants."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.portfolio import (
    apply_fee_once,
    apply_rebate_once,
    build_fee_journal_entry,
    build_rebate_journal_entry,
)
from pmrp.schemas.identifiers import EventId
from pmrp.schemas.numeric import Money
from pmrp.schemas.portfolio import AccountingJournalEntry, CashBalance

pytestmark = pytest.mark.property

CAPTURED_AT = datetime(2026, 9, 28, 14, 0, tzinfo=UTC)
OCCURRED_AT = datetime(2026, 9, 28, 14, 5, tzinfo=UTC)
CREATED_AT = datetime(2026, 9, 28, 14, 5, 1, tzinfo=UTC)

_MONEY = st.integers(min_value=1, max_value=1_000_000).map(
    lambda cents: Decimal(cents) / Decimal("100")
)
_AVAILABLE = st.integers(min_value=-1_000_000, max_value=1_000_000).map(
    lambda cents: Decimal(cents) / Decimal("100")
)
_RESERVED = st.integers(min_value=0, max_value=1_000_000).map(
    lambda cents: Decimal(cents) / Decimal("100")
)


@given(amount=_MONEY)
def test_fee_journal_entry_balances(amount: Decimal) -> None:
    journal = build_fee_journal_entry(
        amount=_money(amount),
        fee_id="fee_property_001",
        source_event_id=EventId("evt_fee_property_001"),
        occurred_at=OCCURRED_AT,
        created_at=CREATED_AT,
    )

    assert _journal_total(journal) == Decimal("0")


@given(amount=_MONEY)
def test_rebate_journal_entry_balances(amount: Decimal) -> None:
    journal = build_rebate_journal_entry(
        amount=_money(amount),
        rebate_id="rebate_property_001",
        source_event_id=EventId("evt_rebate_property_001"),
        occurred_at=OCCURRED_AT,
        created_at=CREATED_AT,
    )

    assert _journal_total(journal) == Decimal("0")


@given(amount=_MONEY, available=_AVAILABLE, reserved=_RESERVED)
def test_apply_fee_once_moves_cash_exactly(
    amount: Decimal,
    available: Decimal,
    reserved: Decimal,
) -> None:
    balance = _balance(available=available, reserved=reserved)

    result = apply_fee_once(
        balance=balance,
        amount=_money(amount),
        fee_id="fee_property_001",
        applied_journal_entry_ids=frozenset(),
        source_event_id=EventId("evt_fee_property_001"),
        occurred_at=OCCURRED_AT,
        created_at=CREATED_AT,
    )

    assert result.balance.available == available - amount
    assert result.balance.reserved == reserved
    assert result.balance.total == result.balance.available + reserved


@given(amount=_MONEY, available=_AVAILABLE, reserved=_RESERVED)
def test_apply_rebate_once_moves_cash_exactly(
    amount: Decimal,
    available: Decimal,
    reserved: Decimal,
) -> None:
    balance = _balance(available=available, reserved=reserved)

    result = apply_rebate_once(
        balance=balance,
        amount=_money(amount),
        rebate_id="rebate_property_001",
        applied_journal_entry_ids=frozenset(),
        source_event_id=EventId("evt_rebate_property_001"),
        occurred_at=OCCURRED_AT,
        created_at=CREATED_AT,
    )

    assert result.balance.available == available + amount
    assert result.balance.reserved == reserved
    assert result.balance.total == result.balance.available + reserved


def _money(amount: Decimal) -> Money:
    return Money(amount=amount, currency="USD")


def _balance(*, available: Decimal, reserved: Decimal) -> CashBalance:
    return CashBalance(
        balance_id="cash_fee_property_usd",
        exchange="kalshi",
        account_id="acct_fee_property_001",
        currency="USD",
        available=available,
        reserved=reserved,
        total=available + reserved,
        captured_at=CAPTURED_AT,
    )


def _journal_total(journal: AccountingJournalEntry) -> Decimal:
    return sum((line.amount for line in journal.lines), start=Decimal("0"))
