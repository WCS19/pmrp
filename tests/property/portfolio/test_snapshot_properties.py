"""Property tests for portfolio snapshot aggregation."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.portfolio import build_portfolio_snapshot
from pmrp.schemas.numeric import Money
from pmrp.schemas.portfolio import CashBalance, Position

pytestmark = pytest.mark.property

CAPTURED_AT = datetime(2026, 9, 26, 14, 0, tzinfo=UTC)
STATE_AT = datetime(2026, 9, 26, 13, 59, tzinfo=UTC)

_QUANTITIES = st.integers(min_value=-1_000, max_value=1_000).map(Decimal)
_PRICES = st.integers(min_value=0, max_value=10_000).map(
    lambda ticks: Decimal(ticks) / Decimal("10000")
)
_MONEY = st.integers(min_value=-1_000_000, max_value=1_000_000).map(
    lambda cents: Decimal(cents) / Decimal("100")
)


@given(
    first_quantity=_QUANTITIES,
    first_price=_PRICES,
    first_realized=_MONEY,
    first_unrealized=_MONEY,
    second_quantity=_QUANTITIES,
    second_price=_PRICES,
    second_realized=_MONEY,
    second_unrealized=_MONEY,
)
def test_build_portfolio_snapshot_aggregates_generated_positions_exactly(
    first_quantity: Decimal,
    first_price: Decimal,
    first_realized: Decimal,
    first_unrealized: Decimal,
    second_quantity: Decimal,
    second_price: Decimal,
    second_realized: Decimal,
    second_unrealized: Decimal,
) -> None:
    first = _position(
        position_id="pos_property_snapshot_a",
        quantity=first_quantity,
        average_entry_price=first_price,
        realized_pnl=first_realized,
        unrealized_pnl=first_unrealized,
    )
    second = _position(
        position_id="pos_property_snapshot_b",
        quantity=second_quantity,
        average_entry_price=second_price,
        realized_pnl=second_realized,
        unrealized_pnl=second_unrealized,
    )

    snapshot = build_portfolio_snapshot(
        portfolio_id="portfolio_property_snapshot",
        positions=(second, first),
        balances=(_balance("cash_property_snapshot_b"), _balance("cash_property_snapshot_a")),
        captured_at=CAPTURED_AT,
        reconciliation_status="healthy",
    )

    expected_gross = abs(first_quantity * first_price) + abs(second_quantity * second_price)
    expected_net = (first_quantity * first_price) + (second_quantity * second_price)
    assert tuple(position.position_id for position in snapshot.positions) == (
        "pos_property_snapshot_a",
        "pos_property_snapshot_b",
    )
    assert tuple(balance.balance_id for balance in snapshot.balances) == (
        "cash_property_snapshot_a",
        "cash_property_snapshot_b",
    )
    assert snapshot.realized_pnl == (_money(first_realized + second_realized),)
    assert snapshot.unrealized_pnl == (_money(first_unrealized + second_unrealized),)
    assert snapshot.gross_exposure == (_money(expected_gross),)
    assert snapshot.net_exposure == (_money(expected_net),)


def _position(
    *,
    position_id: str,
    quantity: Decimal,
    average_entry_price: Decimal,
    realized_pnl: Decimal,
    unrealized_pnl: Decimal,
) -> Position:
    return Position(
        position_id=position_id,
        exchange="kalshi",
        account_id="acct_property_snapshot",
        market_id="mkt_property_snapshot",
        contract_id="ctr_property_snapshot",
        outcome_id="out_yes",
        quantity=quantity,
        average_entry_price=average_entry_price,
        realized_pnl=_money(realized_pnl),
        unrealized_pnl=_money(unrealized_pnl),
        fees_paid=_money(Decimal("0")),
        rebates_received=_money(Decimal("0")),
        opened_at=STATE_AT,
        last_updated_at=STATE_AT,
        aggregate_version=1,
    )


def _balance(balance_id: str) -> CashBalance:
    return CashBalance(
        balance_id=balance_id,
        exchange="kalshi",
        account_id="acct_property_snapshot",
        currency="USD",
        available=Decimal("100.00"),
        reserved=Decimal("0"),
        total=Decimal("100.00"),
        captured_at=STATE_AT,
    )


def _money(amount: Decimal) -> Money:
    return Money(amount=amount, currency="USD")
