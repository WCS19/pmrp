"""Property tests for settlement accounting invariants."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from pmrp.portfolio import (
    apply_settlement_once,
    build_settlement_accounting_result,
    build_settlement_journal_entry,
)
from pmrp.schemas.identifiers import EventId
from pmrp.schemas.numeric import Money
from pmrp.schemas.portfolio import (
    AccountingJournalEntry,
    CashBalance,
    Position,
    Settlement,
    SettlementStatus,
)

pytestmark = pytest.mark.property

OPENED_AT = datetime(2026, 9, 25, 14, 0, tzinfo=UTC)
UPDATED_AT = datetime(2026, 9, 25, 14, 5, tzinfo=UTC)
RESOLVED_AT = datetime(2026, 9, 26, 14, 0, tzinfo=UTC)
FINALIZED_AT = datetime(2026, 9, 26, 14, 5, tzinfo=UTC)
SETTLED_AT = datetime(2026, 9, 26, 14, 10, tzinfo=UTC)
CREATED_AT = datetime(2026, 9, 26, 14, 10, 1, tzinfo=UTC)

_QUANTITIES = st.integers(min_value=-1_000, max_value=1_000).map(Decimal)
_PROBABILITY_AMOUNTS = st.integers(min_value=0, max_value=10_000).map(
    lambda ticks: Decimal(ticks) / Decimal("10000")
)


@given(
    quantity=_QUANTITIES,
    average_entry_price=_PROBABILITY_AMOUNTS,
    payout_per_unit=_PROBABILITY_AMOUNTS,
    winning_position=st.booleans(),
)
def test_settlement_accounting_matches_cash_minus_cost_basis(
    quantity: Decimal,
    average_entry_price: Decimal,
    payout_per_unit: Decimal,
    winning_position: bool,
) -> None:
    assume(quantity != Decimal("0"))
    position = _position(quantity=quantity, average_entry_price=average_entry_price)
    settlement = _settlement(
        winning_outcome_ids=("out_yes",) if winning_position else ("out_no",),
        payout_per_unit=payout_per_unit,
    )

    result = build_settlement_accounting_result(
        position=position,
        settlement=settlement,
        currency="USD",
    )

    expected_cash = quantity * (payout_per_unit if winning_position else Decimal("0"))
    expected_cost_basis = quantity * average_entry_price
    assert result.cash_delta.amount == expected_cash
    assert result.position_cost_basis.amount == expected_cost_basis
    assert result.settlement_pnl.amount == expected_cash - expected_cost_basis
    assert result.settled_quantity == abs(quantity)


@given(
    quantity=_QUANTITIES,
    average_entry_price=_PROBABILITY_AMOUNTS,
    payout_per_unit=_PROBABILITY_AMOUNTS,
    winning_position=st.booleans(),
)
def test_settlement_journal_entries_balance(
    quantity: Decimal,
    average_entry_price: Decimal,
    payout_per_unit: Decimal,
    winning_position: bool,
) -> None:
    assume(quantity != Decimal("0"))
    position = _position(quantity=quantity, average_entry_price=average_entry_price)
    settlement = _settlement(
        winning_outcome_ids=("out_yes",) if winning_position else ("out_no",),
        payout_per_unit=payout_per_unit,
    )

    journal = build_settlement_journal_entry(
        position=position,
        settlement=settlement,
        currency="USD",
        source_event_id=EventId("evt_property_settlement_journal"),
        created_at=CREATED_AT,
    )

    assert _journal_total(journal) == Decimal("0")


@given(
    quantity=_QUANTITIES,
    average_entry_price=_PROBABILITY_AMOUNTS,
    payout_per_unit=_PROBABILITY_AMOUNTS,
    available=st.integers(min_value=-1_000_000, max_value=1_000_000).map(
        lambda cents: Decimal(cents) / Decimal("100")
    ),
    reserved=st.integers(min_value=0, max_value=1_000_000).map(
        lambda cents: Decimal(cents) / Decimal("100")
    ),
    winning_position=st.booleans(),
)
def test_apply_settlement_once_closes_position_and_preserves_cash_identity(
    quantity: Decimal,
    average_entry_price: Decimal,
    payout_per_unit: Decimal,
    available: Decimal,
    reserved: Decimal,
    winning_position: bool,
) -> None:
    assume(quantity != Decimal("0"))
    position = _position(quantity=quantity, average_entry_price=average_entry_price)
    cash_balance = _cash_balance(available=available, reserved=reserved)
    settlement = _settlement(
        winning_outcome_ids=("out_yes",) if winning_position else ("out_no",),
        payout_per_unit=payout_per_unit,
    )

    result = apply_settlement_once(
        position=position,
        cash_balance=cash_balance,
        settlement=settlement,
        applied_journal_entry_ids=frozenset(),
        currency="USD",
        source_event_id=EventId("evt_property_settlement_apply"),
        created_at=CREATED_AT,
    )

    expected_cash_delta = quantity * (payout_per_unit if winning_position else Decimal("0"))
    assert result.applied is True
    assert result.position.quantity == Decimal("0")
    assert result.position.average_entry_price is None
    assert result.cash_balance.available == available + expected_cash_delta
    assert result.cash_balance.reserved == reserved
    assert result.cash_balance.total == result.cash_balance.available + result.cash_balance.reserved


def _position(*, quantity: Decimal, average_entry_price: Decimal) -> Position:
    return Position(
        position_id="pos_property_settlement",
        exchange="kalshi",
        account_id="acct_property_settlement",
        market_id="mkt_property_settlement",
        contract_id="ctr_property_settlement",
        outcome_id="out_yes",
        quantity=quantity,
        average_entry_price=average_entry_price,
        realized_pnl=_money("0"),
        unrealized_pnl=_money("0"),
        fees_paid=_money("0"),
        rebates_received=_money("0"),
        opened_at=OPENED_AT,
        last_updated_at=UPDATED_AT,
        aggregate_version=1,
    )


def _settlement(
    *,
    winning_outcome_ids: tuple[str, ...],
    payout_per_unit: Decimal,
) -> Settlement:
    return Settlement(
        settlement_id="set_property_settlement",
        market_id="mkt_property_settlement",
        exchange="kalshi",
        status=SettlementStatus.SETTLED,
        winning_outcome_ids=winning_outcome_ids,
        resolved_at=RESOLVED_AT,
        finalized_at=FINALIZED_AT,
        settled_at=SETTLED_AT,
        payout_per_unit=payout_per_unit,
        source="exchange",
        source_reference="settlement-source-property",
        correction_of_settlement_id=None,
    )


def _money(amount: str) -> Money:
    return Money(amount=Decimal(amount), currency="USD")


def _cash_balance(*, available: Decimal, reserved: Decimal) -> CashBalance:
    return CashBalance(
        balance_id="cash_property_settlement",
        exchange="kalshi",
        account_id="acct_property_settlement",
        currency="USD",
        available=available,
        reserved=reserved,
        total=available + reserved,
        captured_at=UPDATED_AT,
    )


def _journal_total(journal: AccountingJournalEntry) -> Decimal:
    return sum((line.amount for line in journal.lines), start=Decimal("0"))
