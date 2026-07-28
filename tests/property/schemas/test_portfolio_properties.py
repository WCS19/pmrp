from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.schemas.portfolio import AccountingJournalEntry, CashBalance, JournalLine
from pmrp.schemas.serialization import canonical_json, canonical_sha256

pytestmark = pytest.mark.property

_MONEY_DECIMALS = st.decimals(
    min_value=Decimal("-1000000"),
    max_value=Decimal("1000000"),
    allow_nan=False,
    allow_infinity=False,
    places=4,
)

_NONNEGATIVE_DECIMALS = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("1000000"),
    allow_nan=False,
    allow_infinity=False,
    places=4,
)


def _cash_balance_payload(
    *,
    available: Decimal,
    reserved: Decimal,
    total: Decimal,
) -> dict[str, object]:
    return {
        "balance_id": "balance_usd_001",
        "exchange": "kalshi",
        "account_id": "acct_paper_001",
        "currency": "USD",
        "available": str(available),
        "reserved": str(reserved),
        "total": str(total),
        "captured_at": "2026-07-28T15:30:00Z",
    }


def _journal_entry_payload(lines: tuple[dict[str, object], ...]) -> dict[str, object]:
    return {
        "journal_entry_id": "journal_001",
        "occurred_at": "2026-07-28T15:00:02Z",
        "source_event_id": "evt_01j00000000000000000000000",
        "reference_type": "fill",
        "reference_id": "fill_01j00000000000000000000000",
        "lines": lines,
        "description": "Generated balanced accounting entry.",
        "created_at": "2026-07-28T15:00:03Z",
    }


@given(available=_MONEY_DECIMALS, reserved=_NONNEGATIVE_DECIMALS)
def test_cash_balance_accepts_generated_exact_identity(
    available: Decimal,
    reserved: Decimal,
) -> None:
    balance = CashBalance.model_validate(
        _cash_balance_payload(
            available=available,
            reserved=reserved,
            total=available + reserved,
        )
    )

    assert balance.available + balance.reserved == balance.total


@given(available=_MONEY_DECIMALS, reserved=_NONNEGATIVE_DECIMALS)
def test_cash_balance_hash_is_stable_for_generated_identity(
    available: Decimal,
    reserved: Decimal,
) -> None:
    balance = CashBalance.model_validate(
        _cash_balance_payload(
            available=available,
            reserved=reserved,
            total=available + reserved,
        )
    )

    assert canonical_sha256(balance) == canonical_sha256(
        CashBalance.model_validate_json(canonical_json(balance))
    )


@given(amount=_MONEY_DECIMALS.filter(lambda value: value != Decimal("0")))
def test_journal_entry_accepts_generated_balanced_lines(amount: Decimal) -> None:
    journal = AccountingJournalEntry.model_validate(
        _journal_entry_payload(
            (
                {
                    "account_code": "cash",
                    "amount": str(amount),
                    "currency": "USD",
                    "description": None,
                },
                {
                    "account_code": "contracts",
                    "amount": str(-amount),
                    "currency": "USD",
                    "description": None,
                },
            )
        )
    )

    assert sum(line.amount for line in journal.lines) == Decimal("0")
    assert canonical_sha256(journal) == canonical_sha256(
        AccountingJournalEntry.model_validate_json(canonical_json(journal))
    )


@given(amount=_MONEY_DECIMALS)
def test_journal_line_decimal_values_round_trip_exactly(amount: Decimal) -> None:
    line = JournalLine.model_validate(
        {
            "account_code": "cash",
            "amount": str(amount),
            "currency": "USD",
            "description": None,
        }
    )

    assert line.amount == amount
    assert JournalLine.model_validate_json(canonical_json(line)) == line
