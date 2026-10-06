"""Unit tests for cash balance projections."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.portfolio import (
    ACCOUNT_BALANCE_CORRECTION,
    ACCOUNT_CASH,
    ACCOUNT_FEES_PAID,
    ACCOUNT_POSITION_COST,
    BALANCE_CORRECTION_REFERENCE_TYPE,
    PortfolioProjectionError,
    apply_balance_correction_once,
    apply_journal_to_cash_balance,
    apply_journal_to_cash_balance_once,
    build_balance_correction_journal_entry,
    derive_balance_correction_journal_entry_id,
    derive_cash_balance_id,
)
from pmrp.schemas.identifiers import EventId
from pmrp.schemas.portfolio import AccountingJournalEntry, CashBalance, JournalLine

pytestmark = pytest.mark.unit

CAPTURED_AT = datetime(2026, 9, 25, 13, 59, tzinfo=UTC)
OCCURRED_AT = datetime(2026, 9, 25, 14, 0, tzinfo=UTC)
CREATED_AT = datetime(2026, 9, 25, 14, 0, 1, tzinfo=UTC)
CORRECTION_REFERENCE_ID = "recon_balance_correction_001"


def test_apply_journal_to_cash_balance_projects_matching_cash_lines() -> None:
    balance = _balance(available="100.00", reserved="10.00")
    journal = _journal(
        lines=(
            _line(ACCOUNT_CASH, "-4.00"),
            _line(ACCOUNT_POSITION_COST, "4.00"),
            _line(ACCOUNT_CASH, "-0.02"),
            _line(ACCOUNT_FEES_PAID, "0.02"),
            _line(ACCOUNT_CASH, "0.01"),
            _line("rebates_received", "-0.01"),
        )
    )

    result = apply_journal_to_cash_balance(balance, journal)

    assert result.cash_delta.amount == Decimal("-4.01")
    assert result.cash_delta.currency == "USD"
    assert result.balance.balance_id == balance.balance_id
    assert result.balance.exchange == balance.exchange
    assert result.balance.account_id == balance.account_id
    assert result.balance.available == Decimal("95.99")
    assert result.balance.reserved == Decimal("10.00")
    assert result.balance.total == Decimal("105.99")
    assert result.balance.captured_at == OCCURRED_AT


def test_apply_journal_to_cash_balance_ignores_other_currency_cash_lines() -> None:
    balance = _balance(available="100.00", reserved="0")
    journal = _journal(
        lines=(
            _line(ACCOUNT_CASH, "-1.00", currency="EUR"),
            _line("currency_offset", "1.00", currency="EUR"),
            _line(ACCOUNT_CASH, "2.50"),
            _line("trade_offset", "-2.50"),
        )
    )

    result = apply_journal_to_cash_balance(balance, journal)

    assert result.cash_delta.amount == Decimal("2.50")
    assert result.balance.available == Decimal("102.50")
    assert result.balance.total == Decimal("102.50")


def test_apply_journal_to_cash_balance_rejects_missing_cash_line_for_currency() -> None:
    journal = _journal(
        lines=(
            _line(ACCOUNT_POSITION_COST, "1.00"),
            _line("realized_trading_pnl", "-1.00"),
        )
    )

    with pytest.raises(PortfolioProjectionError, match="cash line"):
        apply_journal_to_cash_balance(_balance(), journal)


def test_apply_journal_to_cash_balance_rejects_stale_journal() -> None:
    balance = _balance(captured_at=OCCURRED_AT + timedelta(seconds=1))
    journal = _journal(
        occurred_at=OCCURRED_AT,
        created_at=OCCURRED_AT + timedelta(seconds=2),
        lines=(
            _line(ACCOUNT_CASH, "1.00"),
            _line("trade_offset", "-1.00"),
        ),
    )

    with pytest.raises(PortfolioProjectionError, match="occurred_at"):
        apply_journal_to_cash_balance(balance, journal)


def test_apply_journal_to_cash_balance_once_is_idempotent_for_duplicate_journal() -> None:
    balance = _balance(available="100.00", reserved="0")
    journal = _journal(
        lines=(
            _line(ACCOUNT_CASH, "-4.00"),
            _line(ACCOUNT_POSITION_COST, "4.00"),
        )
    )

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

    assert first.applied is True
    assert first.duplicate_journal_entry is False
    assert first.cash_projection is not None
    assert first.applied_journal_entry_ids == frozenset({journal.journal_entry_id})
    assert duplicate.applied is False
    assert duplicate.duplicate_journal_entry is True
    assert duplicate.balance == first.balance
    assert duplicate.cash_projection is None
    assert duplicate.applied_journal_entry_ids == first.applied_journal_entry_ids


def test_apply_journal_to_cash_balance_once_does_not_mutate_input_ids() -> None:
    existing_ids = {"journal_existing_balance"}
    journal = _journal(
        journal_entry_id="journal_new_balance",
        lines=(
            _line(ACCOUNT_CASH, "1.00"),
            _line("trade_offset", "-1.00"),
        ),
    )

    result = apply_journal_to_cash_balance_once(
        balance=_balance(),
        journal_entry=journal,
        applied_journal_entry_ids=existing_ids,
    )

    assert existing_ids == {"journal_existing_balance"}
    assert result.applied_journal_entry_ids == frozenset(
        {"journal_existing_balance", "journal_new_balance"}
    )


def test_build_balance_correction_journal_entry_balances_positive_drift() -> None:
    balance = _balance(available="100.00", reserved="10.00")
    observed = _balance(available="102.50", reserved="10.00", captured_at=OCCURRED_AT)

    journal = build_balance_correction_journal_entry(
        balance=balance,
        observed_balance=observed,
        reference_id=CORRECTION_REFERENCE_ID,
        source_event_id=EventId("evt_balance_correction_001"),
        created_at=CREATED_AT,
    )

    assert journal.journal_entry_id == derive_balance_correction_journal_entry_id(
        balance=balance,
        observed_balance=observed,
        reference_id=CORRECTION_REFERENCE_ID,
    )
    assert journal.occurred_at == observed.captured_at
    assert journal.reference_type == BALANCE_CORRECTION_REFERENCE_TYPE
    assert journal.reference_id == CORRECTION_REFERENCE_ID
    assert _line_amounts(journal) == [
        (ACCOUNT_CASH, Decimal("2.50")),
        (ACCOUNT_BALANCE_CORRECTION, Decimal("-2.50")),
    ]
    assert _journal_total(journal) == Decimal("0")


def test_build_balance_correction_journal_entry_balances_negative_drift() -> None:
    balance = _balance(available="100.00", reserved="10.00")
    observed = _balance(available="98.75", reserved="10.00", captured_at=OCCURRED_AT)

    journal = build_balance_correction_journal_entry(
        balance=balance,
        observed_balance=observed,
        reference_id=CORRECTION_REFERENCE_ID,
        source_event_id=EventId("evt_balance_correction_002"),
        created_at=CREATED_AT,
    )

    assert _line_amounts(journal) == [
        (ACCOUNT_CASH, Decimal("-1.25")),
        (ACCOUNT_BALANCE_CORRECTION, Decimal("1.25")),
    ]
    assert _journal_total(journal) == Decimal("0")


def test_apply_balance_correction_once_projects_observed_cash_balance() -> None:
    balance = _balance(available="100.00", reserved="10.00")
    observed = _balance(available="102.50", reserved="10.00", captured_at=OCCURRED_AT)

    result = apply_balance_correction_once(
        balance=balance,
        observed_balance=observed,
        applied_journal_entry_ids=frozenset(),
        reference_id=CORRECTION_REFERENCE_ID,
        source_event_id=EventId("evt_balance_correction_003"),
        created_at=CREATED_AT,
    )

    expected_journal_id = derive_balance_correction_journal_entry_id(
        balance=balance,
        observed_balance=observed,
        reference_id=CORRECTION_REFERENCE_ID,
    )
    assert result.applied is True
    assert result.duplicate_correction is False
    assert result.cash_projection is not None
    assert result.journal_entry is not None
    assert result.journal_entry.journal_entry_id == expected_journal_id
    assert result.balance == observed
    assert result.applied_journal_entry_ids == frozenset({expected_journal_id})


def test_apply_balance_correction_once_returns_noop_for_duplicate_correction() -> None:
    balance = _balance(available="100.00", reserved="10.00")
    observed = _balance(available="102.50", reserved="10.00", captured_at=OCCURRED_AT)
    first = apply_balance_correction_once(
        balance=balance,
        observed_balance=observed,
        applied_journal_entry_ids=frozenset(),
        reference_id=CORRECTION_REFERENCE_ID,
        source_event_id=EventId("evt_balance_correction_004"),
        created_at=CREATED_AT,
    )

    duplicate = apply_balance_correction_once(
        balance=first.balance,
        observed_balance=observed,
        applied_journal_entry_ids=first.applied_journal_entry_ids,
        reference_id=CORRECTION_REFERENCE_ID,
        source_event_id=EventId("evt_balance_correction_duplicate"),
        created_at=CREATED_AT + timedelta(seconds=1),
    )

    assert duplicate.applied is False
    assert duplicate.duplicate_correction is True
    assert duplicate.balance == first.balance
    assert duplicate.cash_projection is None
    assert duplicate.journal_entry is None
    assert duplicate.applied_journal_entry_ids == first.applied_journal_entry_ids


def test_apply_balance_correction_once_noops_duplicate_before_stale_validation() -> None:
    balance = _balance(available="100.00", reserved="10.00")
    observed = _balance(available="102.50", reserved="10.00", captured_at=OCCURRED_AT)
    journal_id = derive_balance_correction_journal_entry_id(
        balance=balance,
        observed_balance=observed,
        reference_id=CORRECTION_REFERENCE_ID,
    )
    later_balance = _balance(
        available="200.00",
        reserved="10.00",
        captured_at=OCCURRED_AT + timedelta(seconds=1),
    )

    duplicate = apply_balance_correction_once(
        balance=later_balance,
        observed_balance=observed,
        applied_journal_entry_ids=frozenset({journal_id}),
        reference_id=CORRECTION_REFERENCE_ID,
        source_event_id=EventId("evt_balance_correction_late_duplicate"),
        created_at=CREATED_AT + timedelta(seconds=2),
    )

    assert duplicate.applied is False
    assert duplicate.duplicate_correction is True
    assert duplicate.balance == later_balance
    assert duplicate.cash_projection is None
    assert duplicate.journal_entry is None


def test_build_balance_correction_journal_entry_rejects_zero_cash_delta() -> None:
    balance = _balance(available="100.00", reserved="10.00")
    observed = _balance(available="100.00", reserved="10.00", captured_at=OCCURRED_AT)

    with pytest.raises(PortfolioProjectionError, match="nonzero cash delta"):
        build_balance_correction_journal_entry(
            balance=balance,
            observed_balance=observed,
            reference_id=CORRECTION_REFERENCE_ID,
            source_event_id=EventId("evt_balance_correction_zero"),
            created_at=CREATED_AT,
        )


def test_build_balance_correction_journal_entry_rejects_reserved_drift() -> None:
    balance = _balance(available="100.00", reserved="10.00")
    observed = _balance(available="100.00", reserved="12.00", captured_at=OCCURRED_AT)

    with pytest.raises(PortfolioProjectionError, match="reserved cash"):
        build_balance_correction_journal_entry(
            balance=balance,
            observed_balance=observed,
            reference_id=CORRECTION_REFERENCE_ID,
            source_event_id=EventId("evt_balance_correction_reserved"),
            created_at=CREATED_AT,
        )


def test_build_balance_correction_journal_entry_rejects_stale_observation() -> None:
    balance = _balance(available="100.00", reserved="10.00", captured_at=OCCURRED_AT)
    observed = _balance(available="102.50", reserved="10.00", captured_at=CAPTURED_AT)

    with pytest.raises(PortfolioProjectionError, match="captured_at"):
        build_balance_correction_journal_entry(
            balance=balance,
            observed_balance=observed,
            reference_id=CORRECTION_REFERENCE_ID,
            source_event_id=EventId("evt_balance_correction_stale"),
            created_at=CREATED_AT,
        )


def test_build_balance_correction_journal_entry_rejects_identity_mismatch() -> None:
    balance = _balance(available="100.00", reserved="10.00")
    observed = _balance(
        available="102.50",
        reserved="10.00",
        currency="EUR",
        captured_at=OCCURRED_AT,
    )

    with pytest.raises(PortfolioProjectionError, match="balance_id"):
        build_balance_correction_journal_entry(
            balance=balance,
            observed_balance=observed,
            reference_id=CORRECTION_REFERENCE_ID,
            source_event_id=EventId("evt_balance_correction_currency"),
            created_at=CREATED_AT,
        )


def test_build_balance_correction_journal_entry_rejects_missing_reference_id() -> None:
    balance = _balance(available="100.00", reserved="10.00")
    observed = _balance(available="102.50", reserved="10.00", captured_at=OCCURRED_AT)

    with pytest.raises(PortfolioProjectionError, match="reference_id"):
        build_balance_correction_journal_entry(
            balance=balance,
            observed_balance=observed,
            reference_id="",
            source_event_id=EventId("evt_balance_correction_missing_ref"),
            created_at=CREATED_AT,
        )


def test_derive_cash_balance_id_is_stable() -> None:
    first = derive_cash_balance_id(
        exchange="kalshi",
        account_id="acct_balance_001",
        currency="USD",
    )
    second = derive_cash_balance_id(
        exchange="kalshi",
        account_id="acct_balance_001",
        currency="USD",
    )
    different = derive_cash_balance_id(
        exchange="polymarket",
        account_id="acct_balance_001",
        currency="USD",
    )

    assert first == second
    assert first.startswith("cash_")
    assert first != different


def test_derive_balance_correction_journal_entry_id_is_stable() -> None:
    balance = _balance(available="100.00", reserved="10.00")
    observed = _balance(available="102.50", reserved="10.00", captured_at=OCCURRED_AT)

    first = derive_balance_correction_journal_entry_id(
        balance=balance,
        observed_balance=observed,
        reference_id=CORRECTION_REFERENCE_ID,
    )
    second = derive_balance_correction_journal_entry_id(
        balance=balance,
        observed_balance=observed,
        reference_id=CORRECTION_REFERENCE_ID,
    )
    different = derive_balance_correction_journal_entry_id(
        balance=balance,
        observed_balance=_balance(available="103.00", reserved="10.00", captured_at=OCCURRED_AT),
        reference_id=CORRECTION_REFERENCE_ID,
    )

    assert first == second
    assert first.startswith("journal_balance_correction_")
    assert first != different


def _balance(
    *,
    available: str = "100.00",
    reserved: str = "10.00",
    currency: str = "USD",
    captured_at: datetime = CAPTURED_AT,
) -> CashBalance:
    available_decimal = Decimal(available)
    reserved_decimal = Decimal(reserved)
    return CashBalance(
        balance_id=derive_cash_balance_id(
            exchange="kalshi",
            account_id="acct_balance_001",
            currency=currency,
        ),
        exchange="kalshi",
        account_id="acct_balance_001",
        currency=currency,
        available=available_decimal,
        reserved=reserved_decimal,
        total=available_decimal + reserved_decimal,
        captured_at=captured_at,
    )


def _journal(
    *,
    journal_entry_id: str = "journal_balance_001",
    occurred_at: datetime = OCCURRED_AT,
    created_at: datetime = CREATED_AT,
    lines: tuple[JournalLine, ...],
) -> AccountingJournalEntry:
    return AccountingJournalEntry(
        journal_entry_id=journal_entry_id,
        occurred_at=occurred_at,
        source_event_id=EventId("evt_balance_journal_001"),
        reference_type="fill",
        reference_id="fill_balance_001",
        lines=lines,
        description="Cash balance projection test journal.",
        created_at=created_at,
    )


def _line(account_code: str, amount: str, *, currency: str = "USD") -> JournalLine:
    return JournalLine(
        account_code=account_code,
        amount=amount,
        currency=currency,
        description=f"{account_code} line",
    )


def _line_amounts(journal: AccountingJournalEntry) -> list[tuple[str, Decimal]]:
    return [(line.account_code, line.amount) for line in journal.lines]


def _journal_total(journal: AccountingJournalEntry) -> Decimal:
    return sum((line.amount for line in journal.lines), start=Decimal("0"))
