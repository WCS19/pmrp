"""Property tests for cash transfer accounting invariants."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.portfolio import apply_cash_transfer_once, build_cash_transfer_journal_entries
from pmrp.schemas.identifiers import EventId
from pmrp.schemas.numeric import Money
from pmrp.schemas.portfolio import AccountingJournalEntry, CashBalance

pytestmark = pytest.mark.property

CAPTURED_AT = datetime(2026, 9, 27, 14, 0, tzinfo=UTC)
OCCURRED_AT = datetime(2026, 9, 27, 14, 5, tzinfo=UTC)
CREATED_AT = datetime(2026, 9, 27, 14, 5, 1, tzinfo=UTC)

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
def test_cash_transfer_journal_entries_balance(amount: Decimal) -> None:
    journals = build_cash_transfer_journal_entries(
        from_balance=_balance("cash_property_transfer_from", available=Decimal("100")),
        to_balance=_balance("cash_property_transfer_to", available=Decimal("20")),
        amount=_money(amount),
        transfer_id="transfer_property_cash",
        source_event_id=EventId("evt_property_cash_transfer"),
        occurred_at=OCCURRED_AT,
        created_at=CREATED_AT,
    )

    assert _journal_total(journals.outbound_journal_entry) == Decimal("0")
    assert _journal_total(journals.inbound_journal_entry) == Decimal("0")


@given(
    amount=_MONEY,
    from_available=_AVAILABLE,
    from_reserved=_RESERVED,
    to_available=_AVAILABLE,
    to_reserved=_RESERVED,
)
def test_apply_cash_transfer_once_moves_cash_and_preserves_balance_identities(
    amount: Decimal,
    from_available: Decimal,
    from_reserved: Decimal,
    to_available: Decimal,
    to_reserved: Decimal,
) -> None:
    from_balance = _balance(
        "cash_property_transfer_from",
        available=from_available,
        reserved=from_reserved,
    )
    to_balance = _balance(
        "cash_property_transfer_to",
        available=to_available,
        reserved=to_reserved,
    )

    result = apply_cash_transfer_once(
        from_balance=from_balance,
        to_balance=to_balance,
        amount=_money(amount),
        transfer_id="transfer_property_cash",
        applied_journal_entry_ids=frozenset(),
        source_event_id=EventId("evt_property_cash_transfer"),
        occurred_at=OCCURRED_AT,
        created_at=CREATED_AT,
    )

    assert result.from_balance.available == from_available - amount
    assert result.from_balance.reserved == from_reserved
    assert result.from_balance.total == result.from_balance.available + from_reserved
    assert result.to_balance.available == to_available + amount
    assert result.to_balance.reserved == to_reserved
    assert result.to_balance.total == result.to_balance.available + to_reserved


def _money(amount: Decimal) -> Money:
    return Money(amount=amount, currency="USD")


def _balance(
    balance_id: str,
    *,
    available: Decimal,
    reserved: Decimal = Decimal("0"),
) -> CashBalance:
    return CashBalance(
        balance_id=balance_id,
        exchange="kalshi",
        account_id=f"acct_{balance_id}",
        currency="USD",
        available=available,
        reserved=reserved,
        total=available + reserved,
        captured_at=CAPTURED_AT,
    )


def _journal_total(journal: AccountingJournalEntry) -> Decimal:
    return sum((line.amount for line in journal.lines), start=Decimal("0"))
