"""Unit tests for deterministic portfolio snapshot construction."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.portfolio import PortfolioProjectionError, build_portfolio_snapshot
from pmrp.schemas.numeric import Money
from pmrp.schemas.portfolio import CashBalance, PortfolioSnapshot, Position

pytestmark = pytest.mark.unit

CAPTURED_AT = datetime(2026, 9, 26, 14, 0, tzinfo=UTC)
POSITION_UPDATED_AT = datetime(2026, 9, 26, 13, 59, tzinfo=UTC)
BALANCE_CAPTURED_AT = datetime(2026, 9, 26, 13, 58, tzinfo=UTC)


def test_build_portfolio_snapshot_aggregates_pnl_and_exposure_by_currency() -> None:
    usd_position = _position(
        position_id="pos_snapshot_usd",
        quantity="10",
        average_entry_price="0.40",
        realized_pnl=_money("0.80"),
        unrealized_pnl=_money("0.15"),
    )
    usd_short = _position(
        position_id="pos_snapshot_usd_short",
        quantity="-5",
        average_entry_price="0.30",
        realized_pnl=_money("-0.10"),
        unrealized_pnl=_money("0.05"),
    )
    eur_position = _position(
        position_id="pos_snapshot_eur",
        quantity="2",
        average_entry_price="0.50",
        realized_pnl=_money("1.00", currency="EUR"),
        unrealized_pnl=_money("0.20", currency="EUR"),
    )

    snapshot = build_portfolio_snapshot(
        portfolio_id="portfolio_snapshot_001",
        positions=(usd_position, usd_short, eur_position),
        balances=(
            _balance(balance_id="cash_snapshot_usd_b", available="20.00"),
            _balance(balance_id="cash_snapshot_usd_a", available="100.00"),
        ),
        captured_at=CAPTURED_AT,
        reconciliation_status="healthy",
    )

    assert isinstance(snapshot, PortfolioSnapshot)
    assert [position.position_id for position in snapshot.positions] == [
        "pos_snapshot_eur",
        "pos_snapshot_usd",
        "pos_snapshot_usd_short",
    ]
    assert [balance.balance_id for balance in snapshot.balances] == [
        "cash_snapshot_usd_a",
        "cash_snapshot_usd_b",
    ]
    assert snapshot.realized_pnl == (_money("1.00", currency="EUR"), _money("0.70"))
    assert snapshot.unrealized_pnl == (_money("0.20", currency="EUR"), _money("0.20"))
    assert snapshot.gross_exposure == (_money("1.00", currency="EUR"), _money("5.50"))
    assert snapshot.net_exposure == (_money("1.00", currency="EUR"), _money("2.50"))
    assert snapshot.reconciliation_status == "healthy"


def test_build_portfolio_snapshot_supports_empty_state() -> None:
    snapshot = build_portfolio_snapshot(
        portfolio_id="portfolio_snapshot_empty",
        positions=(),
        balances=(),
        captured_at=CAPTURED_AT,
        reconciliation_status="healthy",
    )

    assert snapshot.positions == ()
    assert snapshot.balances == ()
    assert snapshot.realized_pnl == ()
    assert snapshot.unrealized_pnl == ()
    assert snapshot.gross_exposure == ()
    assert snapshot.net_exposure == ()


def test_build_portfolio_snapshot_rejects_future_position_state() -> None:
    with pytest.raises(PortfolioProjectionError, match="last_updated_at"):
        build_portfolio_snapshot(
            portfolio_id="portfolio_snapshot_future_position",
            positions=(_position(last_updated_at=CAPTURED_AT + timedelta(seconds=1)),),
            balances=(),
            captured_at=CAPTURED_AT,
            reconciliation_status="healthy",
        )


def test_build_portfolio_snapshot_rejects_future_balance_state() -> None:
    with pytest.raises(PortfolioProjectionError, match="balance captured_at"):
        build_portfolio_snapshot(
            portfolio_id="portfolio_snapshot_future_balance",
            positions=(),
            balances=(_balance(captured_at=CAPTURED_AT + timedelta(seconds=1)),),
            captured_at=CAPTURED_AT,
            reconciliation_status="healthy",
        )


def test_build_portfolio_snapshot_rejects_missing_average_for_nonzero_position() -> None:
    with pytest.raises(PortfolioProjectionError, match="average_entry_price"):
        build_portfolio_snapshot(
            portfolio_id="portfolio_snapshot_missing_average",
            positions=(_position(average_entry_price=None),),
            balances=(),
            captured_at=CAPTURED_AT,
            reconciliation_status="healthy",
        )


def test_build_portfolio_snapshot_rejects_position_currency_mismatch() -> None:
    position = _position(
        realized_pnl=_money("0", currency="USD"),
        unrealized_pnl=_money("0", currency="EUR"),
    )

    with pytest.raises(PortfolioProjectionError, match="currency"):
        build_portfolio_snapshot(
            portfolio_id="portfolio_snapshot_currency_mismatch",
            positions=(position,),
            balances=(),
            captured_at=CAPTURED_AT,
            reconciliation_status="healthy",
        )


def _position(
    *,
    position_id: str = "pos_snapshot_001",
    quantity: str = "10",
    average_entry_price: str | None = "0.40",
    realized_pnl: Money | None = None,
    unrealized_pnl: Money | None = None,
    last_updated_at: datetime = POSITION_UPDATED_AT,
) -> Position:
    money_currency = (realized_pnl or _money("0")).currency
    return Position(
        position_id=position_id,
        exchange="kalshi",
        account_id="acct_snapshot_001",
        market_id="mkt_snapshot_001",
        contract_id="ctr_snapshot_001",
        outcome_id="out_yes",
        quantity=Decimal(quantity),
        average_entry_price=Decimal(average_entry_price)
        if average_entry_price is not None
        else None,
        realized_pnl=realized_pnl or _money("0"),
        unrealized_pnl=unrealized_pnl or _money("0"),
        fees_paid=_money("0", currency=money_currency),
        rebates_received=_money("0", currency=money_currency),
        opened_at=POSITION_UPDATED_AT,
        last_updated_at=last_updated_at,
        aggregate_version=1,
    )


def _balance(
    *,
    balance_id: str = "cash_snapshot_001",
    available: str = "100.00",
    reserved: str = "5.00",
    captured_at: datetime = BALANCE_CAPTURED_AT,
) -> CashBalance:
    available_decimal = Decimal(available)
    reserved_decimal = Decimal(reserved)
    return CashBalance(
        balance_id=balance_id,
        exchange="kalshi",
        account_id="acct_snapshot_001",
        currency="USD",
        available=available_decimal,
        reserved=reserved_decimal,
        total=available_decimal + reserved_decimal,
        captured_at=captured_at,
    )


def _money(amount: str, *, currency: str = "USD") -> Money:
    return Money(amount=Decimal(amount), currency=currency)
