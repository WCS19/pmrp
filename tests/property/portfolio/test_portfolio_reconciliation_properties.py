"""Property tests for portfolio reconciliation helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from pmrp.portfolio import reconcile_portfolio_snapshots
from pmrp.schemas.numeric import Money
from pmrp.schemas.portfolio import CashBalance, PortfolioSnapshot, Position, ReconciliationStatus

pytestmark = pytest.mark.property

STARTED_AT = datetime(2026, 9, 26, 14, 0, tzinfo=UTC)
COMPLETED_AT = datetime(2026, 9, 26, 14, 0, 1, tzinfo=UTC)
CAPTURED_AT = datetime(2026, 9, 26, 13, 59, tzinfo=UTC)

_MONEY_AMOUNTS = st.integers(min_value=-1_000_000, max_value=1_000_000).map(
    lambda cents: Decimal(cents) / Decimal("100")
)
_NONNEGATIVE_MONEY_AMOUNTS = st.integers(min_value=0, max_value=1_000_000).map(
    lambda cents: Decimal(cents) / Decimal("100")
)
_QUANTITIES = st.integers(min_value=1, max_value=1_000).map(Decimal)
_PRICES = st.integers(min_value=0, max_value=10_000).map(
    lambda ticks: Decimal(ticks) / Decimal("10000")
)


@given(
    quantity=_QUANTITIES,
    average_entry_price=_PRICES,
    available=_MONEY_AMOUNTS,
    reserved=_NONNEGATIVE_MONEY_AMOUNTS,
)
def test_reconcile_portfolio_snapshots_releases_gate_for_identical_snapshots(
    quantity: Decimal,
    average_entry_price: Decimal,
    available: Decimal,
    reserved: Decimal,
) -> None:
    snapshot = _snapshot(
        position=_position(quantity=quantity, average_entry_price=average_entry_price),
        balance=_balance(available=available, reserved=reserved),
    )

    result = reconcile_portfolio_snapshots(
        reconciliation_id="recon_property_match",
        exchange="kalshi",
        account_id="acct_property_recon",
        local_snapshot=snapshot,
        external_snapshot=snapshot,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
    )

    assert result.status is ReconciliationStatus.HEALTHY
    assert result.trading_gate_released is True
    assert result.mismatches == ()


@given(
    local_available=_MONEY_AMOUNTS,
    external_available=_MONEY_AMOUNTS,
    reserved=_NONNEGATIVE_MONEY_AMOUNTS,
)
def test_reconcile_portfolio_snapshots_blocks_gate_for_balance_mismatch(
    local_available: Decimal,
    external_available: Decimal,
    reserved: Decimal,
) -> None:
    assume(local_available != external_available)
    local = _snapshot(balance=_balance(available=local_available, reserved=reserved))
    external = _snapshot(balance=_balance(available=external_available, reserved=reserved))

    result = reconcile_portfolio_snapshots(
        reconciliation_id="recon_property_balance_mismatch",
        exchange="kalshi",
        account_id="acct_property_recon",
        local_snapshot=local,
        external_snapshot=external,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
    )

    assert result.status is ReconciliationStatus.MISMATCH
    assert result.trading_gate_released is False
    assert any(mismatch.category == "balance.available" for mismatch in result.mismatches)


def _snapshot(
    *,
    position: Position | None = None,
    balance: CashBalance | None = None,
) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        portfolio_id="portfolio_property_recon",
        captured_at=CAPTURED_AT,
        positions=(position or _position(),),
        balances=(balance or _balance(),),
        realized_pnl=(_money(Decimal("0")),),
        unrealized_pnl=(_money(Decimal("0")),),
        gross_exposure=(_money(Decimal("4.00")),),
        net_exposure=(_money(Decimal("4.00")),),
        reconciliation_status="healthy",
    )


def _position(
    *,
    quantity: Decimal = Decimal("10"),
    average_entry_price: Decimal = Decimal("0.40"),
) -> Position:
    return Position(
        position_id="pos_property_recon",
        exchange="kalshi",
        account_id="acct_property_recon",
        market_id="mkt_property_recon",
        contract_id="ctr_property_recon",
        outcome_id="out_yes",
        quantity=quantity,
        average_entry_price=average_entry_price,
        realized_pnl=_money(Decimal("0")),
        unrealized_pnl=_money(Decimal("0")),
        fees_paid=_money(Decimal("0")),
        rebates_received=_money(Decimal("0")),
        opened_at=CAPTURED_AT,
        last_updated_at=CAPTURED_AT,
        aggregate_version=1,
    )


def _balance(
    *,
    available: Decimal = Decimal("100.00"),
    reserved: Decimal = Decimal("5.00"),
) -> CashBalance:
    return CashBalance(
        balance_id="cash_property_recon",
        exchange="kalshi",
        account_id="acct_property_recon",
        currency="USD",
        available=available,
        reserved=reserved,
        total=available + reserved,
        captured_at=CAPTURED_AT,
    )


def _money(amount: Decimal) -> Money:
    return Money(amount=amount, currency="USD")
