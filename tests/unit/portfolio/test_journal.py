"""Unit tests for fill accounting journal construction."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.portfolio import (
    ACCOUNT_CASH,
    ACCOUNT_FEES_PAID,
    ACCOUNT_POSITION_COST,
    ACCOUNT_REALIZED_TRADING_PNL,
    ACCOUNT_REBATES_RECEIVED,
    FILL_REFERENCE_TYPE,
    PortfolioProjectionError,
    apply_fill_to_position,
    build_fill_journal_entry,
    derive_fill_journal_entry_id,
)
from pmrp.schemas.enums import LiquidityRole, Side
from pmrp.schemas.identifiers import EventId
from pmrp.schemas.numeric import Money
from pmrp.schemas.orders import Fill
from pmrp.schemas.portfolio import AccountingJournalEntry

pytestmark = pytest.mark.unit

OCCURRED_AT = datetime(2026, 9, 25, 14, 0, tzinfo=UTC)
RECEIVED_AT = datetime(2026, 9, 25, 14, 0, 1, tzinfo=UTC)
CREATED_AT = datetime(2026, 9, 25, 14, 0, 2, tzinfo=UTC)
SOURCE_EVENT_ID = EventId("evt_fill_event_001")


def test_build_fill_journal_entry_balances_first_buy_with_fee_and_rebate() -> None:
    fill = _fill(
        price="0.40",
        quantity="10",
        fee=_money("0.02"),
        rebate=_money("0.01"),
    )
    projection = apply_fill_to_position(None, fill, currency="USD")

    journal = build_fill_journal_entry(
        fill=fill,
        projection=projection,
        source_event_id=SOURCE_EVENT_ID,
        created_at=CREATED_AT,
    )

    assert journal.journal_entry_id == derive_fill_journal_entry_id(fill)
    assert journal.occurred_at == OCCURRED_AT
    assert journal.source_event_id == SOURCE_EVENT_ID
    assert journal.reference_type == FILL_REFERENCE_TYPE
    assert journal.reference_id == fill.fill_id
    assert _line_amounts(journal) == [
        (ACCOUNT_CASH, Decimal("-4.00")),
        (ACCOUNT_POSITION_COST, Decimal("4.00")),
        (ACCOUNT_CASH, Decimal("-0.02")),
        (ACCOUNT_FEES_PAID, Decimal("0.02")),
        (ACCOUNT_CASH, Decimal("0.01")),
        (ACCOUNT_REBATES_RECEIVED, Decimal("-0.01")),
    ]
    assert _journal_total(journal) == Decimal("0")


def test_build_fill_journal_entry_balances_long_reduction_gain() -> None:
    first = apply_fill_to_position(None, _fill(price="0.40", quantity="10"), currency="USD")
    closing_fill = _fill(
        fill_id="fill_journal_sell_001",
        exchange_fill_id="ex-fill-sell-001",
        side=Side.SELL,
        price="0.60",
        quantity="4",
        exchange_occurred_at=OCCURRED_AT + timedelta(seconds=1),
        received_at=RECEIVED_AT + timedelta(seconds=1),
    )
    projection = apply_fill_to_position(first.position, closing_fill, currency="USD")

    journal = build_fill_journal_entry(
        fill=closing_fill,
        projection=projection,
        source_event_id=EventId("evt_fill_event_002"),
        created_at=CREATED_AT + timedelta(seconds=1),
    )

    assert _line_amounts(journal) == [
        (ACCOUNT_CASH, Decimal("2.40")),
        (ACCOUNT_POSITION_COST, Decimal("-1.60")),
        (ACCOUNT_REALIZED_TRADING_PNL, Decimal("-0.80")),
    ]
    assert _journal_total(journal) == Decimal("0")


def test_build_fill_journal_entry_balances_short_open_and_cover_gain() -> None:
    short_fill = _fill(side=Side.SELL, price="0.70", quantity="10")
    first = apply_fill_to_position(None, short_fill, currency="USD")
    opening_journal = build_fill_journal_entry(
        fill=short_fill,
        projection=first,
        source_event_id=SOURCE_EVENT_ID,
        created_at=CREATED_AT,
    )

    cover_fill = _fill(
        fill_id="fill_journal_cover_001",
        exchange_fill_id="ex-fill-cover-001",
        side=Side.BUY,
        price="0.40",
        quantity="4",
        exchange_occurred_at=OCCURRED_AT + timedelta(seconds=1),
        received_at=RECEIVED_AT + timedelta(seconds=1),
    )
    cover = apply_fill_to_position(first.position, cover_fill, currency="USD")
    cover_journal = build_fill_journal_entry(
        fill=cover_fill,
        projection=cover,
        source_event_id=EventId("evt_fill_event_003"),
        created_at=CREATED_AT + timedelta(seconds=1),
    )

    assert _line_amounts(opening_journal) == [
        (ACCOUNT_CASH, Decimal("7.00")),
        (ACCOUNT_POSITION_COST, Decimal("-7.00")),
    ]
    assert _journal_total(opening_journal) == Decimal("0")
    assert _line_amounts(cover_journal) == [
        (ACCOUNT_CASH, Decimal("-1.60")),
        (ACCOUNT_POSITION_COST, Decimal("2.80")),
        (ACCOUNT_REALIZED_TRADING_PNL, Decimal("-1.20")),
    ]
    assert _journal_total(cover_journal) == Decimal("0")


def test_build_fill_journal_entry_balances_reversal() -> None:
    first = apply_fill_to_position(None, _fill(price="0.40", quantity="10"), currency="USD")
    reversal_fill = _fill(
        fill_id="fill_journal_reversal_001",
        exchange_fill_id="ex-fill-reversal-001",
        side=Side.SELL,
        price="0.50",
        quantity="15",
        exchange_occurred_at=OCCURRED_AT + timedelta(seconds=1),
        received_at=RECEIVED_AT + timedelta(seconds=1),
    )
    projection = apply_fill_to_position(first.position, reversal_fill, currency="USD")

    journal = build_fill_journal_entry(
        fill=reversal_fill,
        projection=projection,
        source_event_id=EventId("evt_fill_event_004"),
        created_at=CREATED_AT + timedelta(seconds=1),
    )

    assert _line_amounts(journal) == [
        (ACCOUNT_CASH, Decimal("7.50")),
        (ACCOUNT_POSITION_COST, Decimal("-4.00")),
        (ACCOUNT_REALIZED_TRADING_PNL, Decimal("-1.00")),
        (ACCOUNT_POSITION_COST, Decimal("-2.50")),
    ]
    assert _journal_total(journal) == Decimal("0")


def test_build_fill_journal_entry_rejects_mismatched_projection_notional() -> None:
    fill = _fill(price="0.40", quantity="10")
    projection = apply_fill_to_position(None, fill, currency="USD")
    mismatched_projection = projection.__class__(
        position=projection.position,
        realized_trading_pnl=projection.realized_trading_pnl,
        fee=projection.fee,
        rebate=projection.rebate,
        trade_notional=_money("999.00"),
        closed_quantity=projection.closed_quantity,
        opened_quantity=projection.opened_quantity,
        closed_cost_basis=projection.closed_cost_basis,
        closed_trade_value=projection.closed_trade_value,
        opened_notional=projection.opened_notional,
    )

    with pytest.raises(PortfolioProjectionError, match="trade_notional"):
        build_fill_journal_entry(
            fill=fill,
            projection=mismatched_projection,
            source_event_id=SOURCE_EVENT_ID,
            created_at=CREATED_AT,
        )


def test_build_fill_journal_entry_rejects_mismatched_projection_fee() -> None:
    fill = _fill(price="0.40", quantity="10", fee=_money("0.02"))
    projection = apply_fill_to_position(None, fill, currency="USD")
    mismatched_projection = projection.__class__(
        position=projection.position,
        realized_trading_pnl=projection.realized_trading_pnl,
        fee=_money("0.03"),
        rebate=projection.rebate,
        trade_notional=projection.trade_notional,
        closed_quantity=projection.closed_quantity,
        opened_quantity=projection.opened_quantity,
        closed_cost_basis=projection.closed_cost_basis,
        closed_trade_value=projection.closed_trade_value,
        opened_notional=projection.opened_notional,
    )

    with pytest.raises(PortfolioProjectionError, match="fee"):
        build_fill_journal_entry(
            fill=fill,
            projection=mismatched_projection,
            source_event_id=SOURCE_EVENT_ID,
            created_at=CREATED_AT,
        )


def _line_amounts(journal: AccountingJournalEntry) -> list[tuple[str, Decimal]]:
    return [(line.account_code, line.amount) for line in journal.lines]


def _journal_total(journal: AccountingJournalEntry) -> Decimal:
    return sum((line.amount for line in journal.lines), Decimal("0"))


def _fill(
    *,
    fill_id: str = "fill_journal_001",
    exchange_fill_id: str = "ex-fill-journal-001",
    side: Side = Side.BUY,
    price: str = "0.40",
    quantity: str = "10",
    fee: Money | None = None,
    rebate: Money | None = None,
    exchange_occurred_at: datetime = OCCURRED_AT,
    received_at: datetime = RECEIVED_AT,
) -> Fill:
    return Fill(
        fill_id=fill_id,
        exchange_fill_id=exchange_fill_id,
        order_id="ord_journal_order_001",
        exchange_order_id="exchange-order-journal-001",
        client_order_id="client-order-journal-001",
        exchange="kalshi",
        account_id="acct_journal_001",
        market_id="mkt_journal_001",
        contract_id="ctr_journal_001",
        outcome_id="out_yes",
        side=side,
        price=price,
        quantity=quantity,
        liquidity_role=LiquidityRole.UNKNOWN,
        fee=fee,
        rebate=rebate,
        exchange_occurred_at=exchange_occurred_at,
        received_at=received_at,
        trade_id=None,
    )


def _money(amount: str, *, currency: str = "USD") -> Money:
    return Money(amount=Decimal(amount), currency=currency)
