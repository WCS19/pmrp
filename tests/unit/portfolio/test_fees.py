"""Unit tests for standalone portfolio fee and rebate accounting."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.portfolio import (
    ACCOUNT_CASH,
    ACCOUNT_FEES_PAID,
    ACCOUNT_REBATES_RECEIVED,
    FEE_REFERENCE_TYPE,
    REBATE_REFERENCE_TYPE,
    PortfolioProjectionError,
    apply_fee_once,
    apply_rebate_once,
    build_fee_journal_entry,
    build_journal_pnl_attribution,
    build_rebate_journal_entry,
    derive_fee_journal_entry_id,
    derive_rebate_journal_entry_id,
)
from pmrp.schemas.identifiers import EventId
from pmrp.schemas.numeric import Money
from pmrp.schemas.portfolio import AccountingJournalEntry, CashBalance

pytestmark = pytest.mark.unit

CAPTURED_AT = datetime(2026, 9, 28, 14, 0, tzinfo=UTC)
OCCURRED_AT = datetime(2026, 9, 28, 14, 5, tzinfo=UTC)
CREATED_AT = datetime(2026, 9, 28, 14, 5, 1, tzinfo=UTC)
ENDS_AT = datetime(2026, 9, 28, 15, 0, tzinfo=UTC)
SOURCE_EVENT_ID = EventId("evt_fee_rebate_001")
FEE_ID = "fee_standalone_001"
REBATE_ID = "rebate_standalone_001"


def test_build_fee_journal_entry_balances_cash_and_fee_expense() -> None:
    journal = build_fee_journal_entry(
        amount=_money("0.03"),
        fee_id=FEE_ID,
        source_event_id=SOURCE_EVENT_ID,
        occurred_at=OCCURRED_AT,
        created_at=CREATED_AT,
    )

    assert journal.journal_entry_id == derive_fee_journal_entry_id(fee_id=FEE_ID)
    assert journal.source_event_id == SOURCE_EVENT_ID
    assert journal.reference_type == FEE_REFERENCE_TYPE
    assert journal.reference_id == FEE_ID
    assert _line_amounts(journal) == [
        (ACCOUNT_CASH, Decimal("-0.03")),
        (ACCOUNT_FEES_PAID, Decimal("0.03")),
    ]
    assert _journal_total(journal) == Decimal("0")


def test_build_rebate_journal_entry_balances_cash_and_rebate_income() -> None:
    journal = build_rebate_journal_entry(
        amount=_money("0.02"),
        rebate_id=REBATE_ID,
        source_event_id=SOURCE_EVENT_ID,
        occurred_at=OCCURRED_AT,
        created_at=CREATED_AT,
    )

    assert journal.journal_entry_id == derive_rebate_journal_entry_id(rebate_id=REBATE_ID)
    assert journal.reference_type == REBATE_REFERENCE_TYPE
    assert journal.reference_id == REBATE_ID
    assert _line_amounts(journal) == [
        (ACCOUNT_CASH, Decimal("0.02")),
        (ACCOUNT_REBATES_RECEIVED, Decimal("-0.02")),
    ]
    assert _journal_total(journal) == Decimal("0")


def test_apply_fee_once_projects_balance_and_is_idempotent() -> None:
    balance = _balance(available="100.00", reserved="5.00")
    first = apply_fee_once(
        balance=balance,
        amount=_money("0.03"),
        fee_id=FEE_ID,
        applied_journal_entry_ids=frozenset(),
        source_event_id=SOURCE_EVENT_ID,
        occurred_at=OCCURRED_AT,
        created_at=CREATED_AT,
    )

    duplicate = apply_fee_once(
        balance=first.balance,
        amount=_money("0.03"),
        fee_id=FEE_ID,
        applied_journal_entry_ids=first.applied_journal_entry_ids,
        source_event_id=EventId("evt_fee_rebate_duplicate"),
        occurred_at=CAPTURED_AT - timedelta(seconds=1),
        created_at=CREATED_AT + timedelta(seconds=1),
    )

    assert first.applied is True
    assert first.duplicate_fee is False
    assert first.balance.available == Decimal("99.97")
    assert first.balance.reserved == Decimal("5.00")
    assert first.balance.total == Decimal("104.97")
    assert first.cash_projection is not None
    assert first.journal_entry is not None
    assert first.applied_journal_entry_ids == frozenset({first.journal_entry.journal_entry_id})
    assert duplicate.applied is False
    assert duplicate.duplicate_fee is True
    assert duplicate.balance == first.balance
    assert duplicate.cash_projection is None
    assert duplicate.journal_entry is None


def test_apply_rebate_once_projects_balance_and_is_idempotent() -> None:
    balance = _balance(available="100.00", reserved="5.00")
    first = apply_rebate_once(
        balance=balance,
        amount=_money("0.02"),
        rebate_id=REBATE_ID,
        applied_journal_entry_ids=frozenset(),
        source_event_id=SOURCE_EVENT_ID,
        occurred_at=OCCURRED_AT,
        created_at=CREATED_AT,
    )

    duplicate = apply_rebate_once(
        balance=first.balance,
        amount=_money("0.02"),
        rebate_id=REBATE_ID,
        applied_journal_entry_ids=first.applied_journal_entry_ids,
        source_event_id=EventId("evt_fee_rebate_rebate_duplicate"),
        occurred_at=CAPTURED_AT - timedelta(seconds=1),
        created_at=CREATED_AT + timedelta(seconds=1),
    )

    assert first.applied is True
    assert first.duplicate_rebate is False
    assert first.balance.available == Decimal("100.02")
    assert first.balance.reserved == Decimal("5.00")
    assert first.balance.total == Decimal("105.02")
    assert first.cash_projection is not None
    assert first.journal_entry is not None
    assert duplicate.applied is False
    assert duplicate.duplicate_rebate is True
    assert duplicate.balance == first.balance
    assert duplicate.cash_projection is None
    assert duplicate.journal_entry is None


def test_fee_and_rebate_journals_feed_pnl_attribution() -> None:
    fee_journal = build_fee_journal_entry(
        amount=_money("0.03"),
        fee_id=FEE_ID,
        source_event_id=SOURCE_EVENT_ID,
        occurred_at=OCCURRED_AT,
        created_at=CREATED_AT,
    )
    rebate_journal = build_rebate_journal_entry(
        amount=_money("0.02"),
        rebate_id=REBATE_ID,
        source_event_id=EventId("evt_fee_rebate_002"),
        occurred_at=OCCURRED_AT + timedelta(seconds=1),
        created_at=CREATED_AT + timedelta(seconds=1),
    )

    attribution = build_journal_pnl_attribution(
        journal_entries=(fee_journal, rebate_journal),
        currency="USD",
        starts_at=CAPTURED_AT,
        ends_at=ENDS_AT,
    )

    assert attribution.fees == _money("0.03")
    assert attribution.rebates == _money("0.02")
    assert attribution.total_pnl == _money("-0.01")


def test_fee_rebate_accounting_rejects_invalid_inputs() -> None:
    with pytest.raises(PortfolioProjectionError, match="fee amount must be positive"):
        build_fee_journal_entry(
            amount=_money("0"),
            fee_id=FEE_ID,
            source_event_id=SOURCE_EVENT_ID,
            occurred_at=OCCURRED_AT,
            created_at=CREATED_AT,
        )
    with pytest.raises(PortfolioProjectionError, match="rebate amount must be positive"):
        build_rebate_journal_entry(
            amount=_money("-0.01"),
            rebate_id=REBATE_ID,
            source_event_id=SOURCE_EVENT_ID,
            occurred_at=OCCURRED_AT,
            created_at=CREATED_AT,
        )
    with pytest.raises(PortfolioProjectionError, match="fee currency"):
        apply_fee_once(
            balance=_balance(currency="USD"),
            amount=_money("0.03", currency="EUR"),
            fee_id=FEE_ID,
            applied_journal_entry_ids=frozenset(),
            source_event_id=SOURCE_EVENT_ID,
            occurred_at=OCCURRED_AT,
            created_at=CREATED_AT,
        )
    with pytest.raises(PortfolioProjectionError, match="fee_id"):
        derive_fee_journal_entry_id(fee_id=" fee_standalone_001")
    with pytest.raises(PortfolioProjectionError, match="rebate_id"):
        derive_rebate_journal_entry_id(rebate_id="r" * 129)


def _money(amount: str, *, currency: str = "USD") -> Money:
    return Money(amount=Decimal(amount), currency=currency)


def _balance(
    *,
    available: str = "100.00",
    reserved: str = "0.00",
    currency: str = "USD",
) -> CashBalance:
    available_decimal = Decimal(available)
    reserved_decimal = Decimal(reserved)
    return CashBalance(
        balance_id=f"cash_fee_rebate_{currency.lower()}",
        exchange="kalshi",
        account_id="acct_fee_rebate_001",
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
