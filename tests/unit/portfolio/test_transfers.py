"""Unit tests for cash transfer accounting helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.portfolio import (
    ACCOUNT_CASH,
    ACCOUNT_CASH_TRANSFER,
    TRANSFER_REFERENCE_TYPE,
    PortfolioProjectionError,
    apply_cash_transfer_once,
    build_cash_transfer_journal_entry,
    derive_cash_transfer_journal_entry_id,
)
from pmrp.schemas.identifiers import EventId
from pmrp.schemas.numeric import Money
from pmrp.schemas.portfolio import AccountingJournalEntry, CashBalance

pytestmark = pytest.mark.unit

CAPTURED_AT = datetime(2026, 9, 27, 14, 0, tzinfo=UTC)
OCCURRED_AT = datetime(2026, 9, 27, 14, 5, tzinfo=UTC)
CREATED_AT = datetime(2026, 9, 27, 14, 5, 1, tzinfo=UTC)
SOURCE_EVENT_ID = EventId("evt_cash_transfer_001")
TRANSFER_ID = "transfer_cash_001"


def test_build_cash_transfer_journal_entry_balances_both_legs() -> None:
    from_balance = _balance("cash_transfer_from", available="100.00")
    to_balance = _balance("cash_transfer_to", available="20.00")

    journal = build_cash_transfer_journal_entry(
        from_balance=from_balance,
        to_balance=to_balance,
        amount=_money("12.50"),
        transfer_id=TRANSFER_ID,
        source_event_id=SOURCE_EVENT_ID,
        occurred_at=OCCURRED_AT,
        created_at=CREATED_AT,
    )

    assert journal.journal_entry_id == derive_cash_transfer_journal_entry_id(
        transfer_id=TRANSFER_ID
    )
    assert journal.source_event_id == SOURCE_EVENT_ID
    assert journal.reference_type == TRANSFER_REFERENCE_TYPE
    assert journal.reference_id == TRANSFER_ID
    assert _line_amounts(journal) == [
        (f"{ACCOUNT_CASH}:{from_balance.balance_id}", Decimal("-12.50")),
        (ACCOUNT_CASH_TRANSFER, Decimal("12.50")),
        (f"{ACCOUNT_CASH}:{to_balance.balance_id}", Decimal("12.50")),
        (ACCOUNT_CASH_TRANSFER, Decimal("-12.50")),
    ]
    assert _journal_total(journal) == Decimal("0")


def test_apply_cash_transfer_once_projects_both_balances() -> None:
    from_balance = _balance("cash_transfer_from", available="100.00", reserved="5.00")
    to_balance = _balance("cash_transfer_to", available="20.00", reserved="3.00")

    result = apply_cash_transfer_once(
        from_balance=from_balance,
        to_balance=to_balance,
        amount=_money("12.50"),
        transfer_id=TRANSFER_ID,
        applied_journal_entry_ids=frozenset(),
        source_event_id=SOURCE_EVENT_ID,
        occurred_at=OCCURRED_AT,
        created_at=CREATED_AT,
    )

    assert result.applied is True
    assert result.duplicate_transfer is False
    assert result.from_balance.available == Decimal("87.50")
    assert result.from_balance.reserved == Decimal("5.00")
    assert result.from_balance.total == Decimal("92.50")
    assert result.to_balance.available == Decimal("32.50")
    assert result.to_balance.reserved == Decimal("3.00")
    assert result.to_balance.total == Decimal("35.50")
    assert result.outbound_projection is not None
    assert result.inbound_projection is not None
    assert result.journal_entry is not None
    assert result.applied_journal_entry_ids == frozenset(
        {
            result.journal_entry.journal_entry_id,
        }
    )


def test_apply_cash_transfer_once_returns_noop_for_duplicate_transfer() -> None:
    from_balance = _balance("cash_transfer_from", available="100.00")
    to_balance = _balance("cash_transfer_to", available="20.00")
    first = apply_cash_transfer_once(
        from_balance=from_balance,
        to_balance=to_balance,
        amount=_money("12.50"),
        transfer_id=TRANSFER_ID,
        applied_journal_entry_ids=frozenset(),
        source_event_id=SOURCE_EVENT_ID,
        occurred_at=OCCURRED_AT,
        created_at=CREATED_AT,
    )

    duplicate = apply_cash_transfer_once(
        from_balance=first.from_balance,
        to_balance=first.to_balance,
        amount=_money("12.50"),
        transfer_id=TRANSFER_ID,
        applied_journal_entry_ids=first.applied_journal_entry_ids,
        source_event_id=EventId("evt_cash_transfer_duplicate"),
        occurred_at=CAPTURED_AT - timedelta(seconds=1),
        created_at=CREATED_AT + timedelta(seconds=1),
    )

    assert duplicate.applied is False
    assert duplicate.duplicate_transfer is True
    assert duplicate.from_balance == first.from_balance
    assert duplicate.to_balance == first.to_balance
    assert duplicate.outbound_projection is None
    assert duplicate.inbound_projection is None
    assert duplicate.journal_entry is None
    assert duplicate.applied_journal_entry_ids == first.applied_journal_entry_ids


def test_transfer_journal_uses_one_source_event_safe_header() -> None:
    from_balance = _balance("cash_transfer_from", available="100.00")
    to_balance = _balance("cash_transfer_to", available="20.00")

    result = apply_cash_transfer_once(
        from_balance=from_balance,
        to_balance=to_balance,
        amount=_money("12.50"),
        transfer_id=TRANSFER_ID,
        applied_journal_entry_ids=frozenset(),
        source_event_id=SOURCE_EVENT_ID,
        occurred_at=OCCURRED_AT,
        created_at=CREATED_AT,
    )

    assert result.journal_entry is not None
    assert result.journal_entry.source_event_id == SOURCE_EVENT_ID
    assert len(result.applied_journal_entry_ids) == 1


def test_build_cash_transfer_journal_entry_rejects_invalid_inputs() -> None:
    from_balance = _balance("cash_transfer_from", available="100.00")
    to_balance = _balance("cash_transfer_to", available="20.00")

    with pytest.raises(PortfolioProjectionError, match="distinct"):
        build_cash_transfer_journal_entry(
            from_balance=from_balance,
            to_balance=from_balance,
            amount=_money("12.50"),
            transfer_id=TRANSFER_ID,
            source_event_id=SOURCE_EVENT_ID,
            occurred_at=OCCURRED_AT,
            created_at=CREATED_AT,
        )
    with pytest.raises(PortfolioProjectionError, match="positive"):
        build_cash_transfer_journal_entry(
            from_balance=from_balance,
            to_balance=to_balance,
            amount=_money("0"),
            transfer_id=TRANSFER_ID,
            source_event_id=SOURCE_EVENT_ID,
            occurred_at=OCCURRED_AT,
            created_at=CREATED_AT,
        )
    with pytest.raises(PortfolioProjectionError, match="currency"):
        build_cash_transfer_journal_entry(
            from_balance=from_balance,
            to_balance=_balance("cash_transfer_to_eur", available="20.00", currency="EUR"),
            amount=_money("12.50"),
            transfer_id=TRANSFER_ID,
            source_event_id=SOURCE_EVENT_ID,
            occurred_at=OCCURRED_AT,
            created_at=CREATED_AT,
        )
    with pytest.raises(PortfolioProjectionError, match="transfer_id"):
        build_cash_transfer_journal_entry(
            from_balance=from_balance,
            to_balance=to_balance,
            amount=_money("12.50"),
            transfer_id=" transfer_cash_001",
            source_event_id=SOURCE_EVENT_ID,
            occurred_at=OCCURRED_AT,
            created_at=CREATED_AT,
        )


def test_derive_cash_transfer_journal_entry_id_rejects_invalid_transfer_id() -> None:
    with pytest.raises(PortfolioProjectionError, match="transfer_id"):
        derive_cash_transfer_journal_entry_id(transfer_id=" transfer_cash_001")


def _money(amount: str, currency: str = "USD") -> Money:
    return Money(amount=Decimal(amount), currency=currency)


def _balance(
    balance_id: str,
    *,
    available: str,
    reserved: str = "0.00",
    currency: str = "USD",
) -> CashBalance:
    available_decimal = Decimal(available)
    reserved_decimal = Decimal(reserved)
    return CashBalance(
        balance_id=balance_id,
        exchange="kalshi",
        account_id=f"acct_{balance_id}",
        currency=currency,
        available=available_decimal,
        reserved=reserved_decimal,
        total=available_decimal + reserved_decimal,
        captured_at=CAPTURED_AT,
    )


def _line_amounts(journal: AccountingJournalEntry) -> list[tuple[str, Decimal]]:
    return [(line.account_code, line.amount) for line in journal.lines]


def _journal_total(journal: AccountingJournalEntry) -> Decimal:
    return sum((line.amount for line in journal.lines), start=Decimal("0"))
