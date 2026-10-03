"""Unit tests for settlement accounting journals."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.portfolio import (
    ACCOUNT_CASH,
    ACCOUNT_POSITION_COST,
    ACCOUNT_SETTLEMENT_PNL,
    SETTLEMENT_REFERENCE_TYPE,
    PortfolioProjectionError,
    apply_settlement_once,
    apply_settlement_to_position,
    build_journal_pnl_attribution,
    build_settlement_accounting_result,
    build_settlement_journal_entry,
    derive_cash_balance_id,
    derive_settlement_journal_entry_id,
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

pytestmark = pytest.mark.unit

OPENED_AT = datetime(2026, 9, 25, 14, 0, tzinfo=UTC)
UPDATED_AT = datetime(2026, 9, 25, 14, 5, tzinfo=UTC)
RESOLVED_AT = datetime(2026, 9, 26, 14, 0, tzinfo=UTC)
FINALIZED_AT = datetime(2026, 9, 26, 14, 5, tzinfo=UTC)
SETTLED_AT = datetime(2026, 9, 26, 14, 10, tzinfo=UTC)
CREATED_AT = datetime(2026, 9, 26, 14, 10, 1, tzinfo=UTC)
SOURCE_EVENT_ID = EventId("evt_settlement_journal_001")


def test_build_settlement_journal_entry_balances_long_win() -> None:
    position = _position(quantity="10", average_entry_price="0.40")
    settlement = _settlement(winning_outcome_ids=("out_yes",), payout_per_unit="1")

    result = build_settlement_accounting_result(
        position=position,
        settlement=settlement,
        currency="USD",
    )
    journal = build_settlement_journal_entry(
        position=position,
        settlement=settlement,
        currency="USD",
        source_event_id=SOURCE_EVENT_ID,
        created_at=CREATED_AT,
    )

    assert result.cash_delta == _money("10")
    assert result.position_cost_basis == _money("4.00")
    assert result.settlement_pnl == _money("6.00")
    assert result.settled_quantity == Decimal("10")
    assert result.winning_position is True
    assert journal.journal_entry_id == derive_settlement_journal_entry_id(position, settlement)
    assert journal.occurred_at == SETTLED_AT
    assert journal.reference_type == SETTLEMENT_REFERENCE_TYPE
    assert journal.reference_id == settlement.settlement_id
    assert _line_amounts(journal) == [
        (ACCOUNT_CASH, Decimal("10")),
        (ACCOUNT_POSITION_COST, Decimal("-4.00")),
        (ACCOUNT_SETTLEMENT_PNL, Decimal("-6.00")),
    ]
    assert _journal_total(journal) == Decimal("0")


def test_build_settlement_journal_entry_balances_long_loss() -> None:
    position = _position(quantity="10", average_entry_price="0.40")
    settlement = _settlement(winning_outcome_ids=("out_no",), payout_per_unit="1")

    result = build_settlement_accounting_result(
        position=position,
        settlement=settlement,
        currency="USD",
    )
    journal = build_settlement_journal_entry(
        position=position,
        settlement=settlement,
        currency="USD",
        source_event_id=SOURCE_EVENT_ID,
        created_at=CREATED_AT,
    )

    assert result.cash_delta == _money("0")
    assert result.position_cost_basis == _money("4.00")
    assert result.settlement_pnl == _money("-4.00")
    assert result.winning_position is False
    assert _line_amounts(journal) == [
        (ACCOUNT_CASH, Decimal("0")),
        (ACCOUNT_POSITION_COST, Decimal("-4.00")),
        (ACCOUNT_SETTLEMENT_PNL, Decimal("4.00")),
    ]
    assert _journal_total(journal) == Decimal("0")


def test_build_settlement_journal_entry_balances_short_win_and_loss() -> None:
    position = _position(quantity="-10", average_entry_price="0.70")
    winning_settlement = _settlement(
        settlement_id="set_settlement_short_win",
        winning_outcome_ids=("out_yes",),
        payout_per_unit="1",
    )
    losing_settlement = _settlement(
        settlement_id="set_settlement_short_loss",
        winning_outcome_ids=("out_no",),
        payout_per_unit="1",
    )

    winning_result = build_settlement_accounting_result(
        position=position,
        settlement=winning_settlement,
        currency="USD",
    )
    losing_result = build_settlement_accounting_result(
        position=position,
        settlement=losing_settlement,
        currency="USD",
    )

    assert winning_result.cash_delta == _money("-10")
    assert winning_result.position_cost_basis == _money("-7.00")
    assert winning_result.settlement_pnl == _money("-3.00")
    assert losing_result.cash_delta == _money("0")
    assert losing_result.position_cost_basis == _money("-7.00")
    assert losing_result.settlement_pnl == _money("7.00")


def test_build_journal_pnl_attribution_includes_settlement_pnl_lines() -> None:
    position = _position(quantity="10", average_entry_price="0.40")
    settlement = _settlement(winning_outcome_ids=("out_yes",), payout_per_unit="1")
    journal = build_settlement_journal_entry(
        position=position,
        settlement=settlement,
        currency="USD",
        source_event_id=SOURCE_EVENT_ID,
        created_at=CREATED_AT,
    )

    attribution = build_journal_pnl_attribution(
        journal_entries=(journal,),
        currency="USD",
        starts_at=SETTLED_AT - timedelta(seconds=1),
        ends_at=SETTLED_AT + timedelta(seconds=1),
    )

    assert attribution.settlement_pnl == _money("6.00")
    assert attribution.total_pnl == _money("6.00")


def test_apply_settlement_to_position_closes_position_and_realizes_settlement_pnl() -> None:
    position = _position(quantity="10", average_entry_price="0.40")
    settlement = _settlement(winning_outcome_ids=("out_yes",), payout_per_unit="1")

    result = apply_settlement_to_position(
        position=position,
        settlement=settlement,
        currency="USD",
    )

    assert result.settlement_accounting.settlement_pnl == _money("6.00")
    assert result.position.position_id == position.position_id
    assert result.position.quantity == Decimal("0")
    assert result.position.average_entry_price is None
    assert result.position.realized_pnl == _money("6.00")
    assert result.position.unrealized_pnl == _money("0")
    assert result.position.fees_paid == position.fees_paid
    assert result.position.rebates_received == position.rebates_received
    assert result.position.opened_at is None
    assert result.position.last_updated_at == SETTLED_AT
    assert result.position.aggregate_version == position.aggregate_version + 1


def test_apply_settlement_once_projects_position_cash_and_journal() -> None:
    position = _position(quantity="10", average_entry_price="0.40")
    cash_balance = _cash_balance(available="100.00", reserved="5.00")
    settlement = _settlement(winning_outcome_ids=("out_yes",), payout_per_unit="1")

    result = apply_settlement_once(
        position=position,
        cash_balance=cash_balance,
        settlement=settlement,
        applied_journal_entry_ids=frozenset(),
        currency="USD",
        source_event_id=SOURCE_EVENT_ID,
        created_at=CREATED_AT,
    )

    expected_journal_id = derive_settlement_journal_entry_id(position, settlement)
    assert result.applied is True
    assert result.duplicate_settlement is False
    assert result.position.quantity == Decimal("0")
    assert result.cash_balance.available == Decimal("110.00")
    assert result.cash_balance.reserved == Decimal("5.00")
    assert result.cash_balance.total == Decimal("115.00")
    assert result.position_projection is not None
    assert result.cash_projection is not None
    assert result.journal_entry is not None
    assert result.journal_entry.journal_entry_id == expected_journal_id
    assert result.applied_journal_entry_ids == frozenset({expected_journal_id})


def test_apply_settlement_once_returns_noop_for_duplicate_journal_id() -> None:
    position = _position(quantity="10", average_entry_price="0.40")
    cash_balance = _cash_balance(available="100.00", reserved="5.00")
    settlement = _settlement(winning_outcome_ids=("out_yes",), payout_per_unit="1")
    first = apply_settlement_once(
        position=position,
        cash_balance=cash_balance,
        settlement=settlement,
        applied_journal_entry_ids=frozenset(),
        currency="USD",
        source_event_id=SOURCE_EVENT_ID,
        created_at=CREATED_AT,
    )

    duplicate = apply_settlement_once(
        position=first.position,
        cash_balance=first.cash_balance,
        settlement=settlement,
        applied_journal_entry_ids=first.applied_journal_entry_ids,
        currency="USD",
        source_event_id=EventId("evt_settlement_journal_duplicate"),
        created_at=CREATED_AT + timedelta(seconds=1),
    )

    assert duplicate.applied is False
    assert duplicate.duplicate_settlement is True
    assert duplicate.position == first.position
    assert duplicate.cash_balance == first.cash_balance
    assert duplicate.position_projection is None
    assert duplicate.cash_projection is None
    assert duplicate.journal_entry is None
    assert duplicate.applied_journal_entry_ids == first.applied_journal_entry_ids


def test_apply_settlement_to_position_rejects_stale_settlement() -> None:
    position = _position(
        quantity="10",
        average_entry_price="0.40",
        last_updated_at=SETTLED_AT + timedelta(seconds=1),
    )
    settlement = _settlement(winning_outcome_ids=("out_yes",), payout_per_unit="1")

    with pytest.raises(PortfolioProjectionError, match="older than the position update horizon"):
        apply_settlement_to_position(
            position=position,
            settlement=settlement,
            currency="USD",
        )


def test_apply_settlement_to_position_rejects_position_currency_mismatch() -> None:
    position = _position(
        quantity="10",
        average_entry_price="0.40",
        realized_pnl=Money(amount=Decimal("0"), currency="EUR"),
    )
    settlement = _settlement(winning_outcome_ids=("out_yes",), payout_per_unit="1")

    with pytest.raises(PortfolioProjectionError, match="realized_pnl currency"):
        apply_settlement_to_position(
            position=position,
            settlement=settlement,
            currency="USD",
        )


def test_apply_settlement_once_rejects_cash_balance_mismatch() -> None:
    position = _position(quantity="10", average_entry_price="0.40")
    cash_balance = _cash_balance(available="100.00", reserved="5.00", account_id="acct_other")
    settlement = _settlement(winning_outcome_ids=("out_yes",), payout_per_unit="1")

    with pytest.raises(PortfolioProjectionError, match="cash balance account_id"):
        apply_settlement_once(
            position=position,
            cash_balance=cash_balance,
            settlement=settlement,
            applied_journal_entry_ids=frozenset(),
            currency="USD",
            source_event_id=SOURCE_EVENT_ID,
            created_at=CREATED_AT,
        )


def test_build_settlement_journal_entry_rejects_unsettled_settlement() -> None:
    position = _position(quantity="10", average_entry_price="0.40")
    settlement = _settlement(
        status=SettlementStatus.FINALIZED,
        settled_at=None,
        winning_outcome_ids=("out_yes",),
        payout_per_unit="1",
    )

    with pytest.raises(PortfolioProjectionError, match="settled settlement status"):
        build_settlement_journal_entry(
            position=position,
            settlement=settlement,
            currency="USD",
            source_event_id=SOURCE_EVENT_ID,
            created_at=CREATED_AT,
        )


def test_build_settlement_journal_entry_rejects_mismatched_market() -> None:
    position = _position(quantity="10", average_entry_price="0.40")
    settlement = _settlement(
        market_id="mkt_other_settlement",
        winning_outcome_ids=("out_yes",),
        payout_per_unit="1",
    )

    with pytest.raises(PortfolioProjectionError, match="market_id"):
        build_settlement_journal_entry(
            position=position,
            settlement=settlement,
            currency="USD",
            source_event_id=SOURCE_EVENT_ID,
            created_at=CREATED_AT,
        )


def test_build_settlement_journal_entry_rejects_missing_average_entry_price() -> None:
    position = _position(quantity="10", average_entry_price=None)
    settlement = _settlement(winning_outcome_ids=("out_yes",), payout_per_unit="1")

    with pytest.raises(PortfolioProjectionError, match="average_entry_price"):
        build_settlement_journal_entry(
            position=position,
            settlement=settlement,
            currency="USD",
            source_event_id=SOURCE_EVENT_ID,
            created_at=CREATED_AT,
        )


def _position(
    *,
    quantity: str,
    average_entry_price: str | None,
    market_id: str = "mkt_settlement_001",
    outcome_id: str = "out_yes",
    exchange: str = "kalshi",
    last_updated_at: datetime = UPDATED_AT,
    realized_pnl: Money | None = None,
) -> Position:
    return Position(
        position_id="pos_settlement_001",
        exchange=exchange,
        account_id="acct_settlement_001",
        market_id=market_id,
        contract_id="ctr_settlement_001",
        outcome_id=outcome_id,
        quantity=quantity,
        average_entry_price=average_entry_price,
        realized_pnl=realized_pnl or _money("0"),
        unrealized_pnl=_money("0"),
        fees_paid=_money("0"),
        rebates_received=_money("0"),
        opened_at=OPENED_AT,
        last_updated_at=last_updated_at,
        aggregate_version=1,
    )


def _settlement(
    *,
    settlement_id: str = "set_settlement_001",
    market_id: str = "mkt_settlement_001",
    exchange: str = "kalshi",
    status: SettlementStatus = SettlementStatus.SETTLED,
    winning_outcome_ids: tuple[str, ...],
    payout_per_unit: str,
    settled_at: datetime | None = SETTLED_AT,
) -> Settlement:
    return Settlement(
        settlement_id=settlement_id,
        market_id=market_id,
        exchange=exchange,
        status=status,
        winning_outcome_ids=winning_outcome_ids,
        resolved_at=RESOLVED_AT,
        finalized_at=FINALIZED_AT,
        settled_at=settled_at,
        payout_per_unit=payout_per_unit,
        source="exchange",
        source_reference="settlement-source-001",
        correction_of_settlement_id=None,
    )


def _money(amount: str) -> Money:
    return Money(amount=Decimal(amount), currency="USD")


def _cash_balance(
    *,
    available: str,
    reserved: str,
    account_id: str = "acct_settlement_001",
) -> CashBalance:
    available_decimal = Decimal(available)
    reserved_decimal = Decimal(reserved)
    return CashBalance(
        balance_id=derive_cash_balance_id(
            exchange="kalshi",
            account_id=account_id,
            currency="USD",
        ),
        exchange="kalshi",
        account_id=account_id,
        currency="USD",
        available=available_decimal,
        reserved=reserved_decimal,
        total=available_decimal + reserved_decimal,
        captured_at=UPDATED_AT,
    )


def _line_amounts(journal: AccountingJournalEntry) -> list[tuple[str, Decimal]]:
    return [(line.account_code, line.amount) for line in journal.lines]


def _journal_total(journal: AccountingJournalEntry) -> Decimal:
    return sum((line.amount for line in journal.lines), start=Decimal("0"))
