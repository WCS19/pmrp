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
    build_journal_pnl_attribution,
    build_settlement_accounting_result,
    build_settlement_journal_entry,
    derive_settlement_journal_entry_id,
)
from pmrp.schemas.identifiers import EventId
from pmrp.schemas.numeric import Money
from pmrp.schemas.portfolio import (
    AccountingJournalEntry,
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


def _line_amounts(journal: AccountingJournalEntry) -> list[tuple[str, Decimal]]:
    return [(line.account_code, line.amount) for line in journal.lines]


def _journal_total(journal: AccountingJournalEntry) -> Decimal:
    return sum((line.amount for line in journal.lines), start=Decimal("0"))
