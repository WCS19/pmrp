"""Unit tests for portfolio position projection."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.portfolio import (
    UNREALIZED_PNL_POLICY,
    WEIGHTED_AVERAGE_COST_METHOD,
    PortfolioProjectionError,
    apply_fill_to_position,
    derive_position_id,
)
from pmrp.schemas.enums import LiquidityRole, Side
from pmrp.schemas.numeric import Money
from pmrp.schemas.orders import Fill
from pmrp.schemas.portfolio import Position

pytestmark = pytest.mark.unit

OCCURRED_AT = datetime(2026, 9, 25, 14, 0, tzinfo=UTC)
RECEIVED_AT = datetime(2026, 9, 25, 14, 0, 1, tzinfo=UTC)


def test_first_buy_fill_opens_long_position() -> None:
    fill = _fill(price="0.40", quantity="10", fee=_money("0.02"))

    result = apply_fill_to_position(None, fill, currency="USD")

    assert result.accounting_method == WEIGHTED_AVERAGE_COST_METHOD
    assert result.unrealized_pnl_policy == UNREALIZED_PNL_POLICY
    assert result.position.position_id == derive_position_id(fill)
    assert result.position.quantity == Decimal("10")
    assert result.position.average_entry_price == Decimal("0.40")
    assert result.position.realized_pnl == _money("0")
    assert result.position.unrealized_pnl == _money("0")
    assert result.position.fees_paid == _money("0.02")
    assert result.position.rebates_received == _money("0")
    assert result.position.opened_at == OCCURRED_AT
    assert result.position.last_updated_at == OCCURRED_AT
    assert result.position.aggregate_version == 1
    assert result.realized_trading_pnl == _money("0")
    assert result.fee == _money("0.02")
    assert result.rebate == _money("0")
    assert result.trade_notional == _money("4.00")
    assert result.closed_quantity == Decimal("0")
    assert result.opened_quantity == Decimal("10")
    assert result.closed_cost_basis == _money("0")
    assert result.closed_trade_value == _money("0")
    assert result.opened_notional == _money("4.00")


def test_derived_position_id_is_stable_for_same_account_contract_identity() -> None:
    first_fill = _fill(fill_id="fill_stable_001", exchange_fill_id="ex-fill-001")
    second_fill = _fill(fill_id="fill_stable_002", exchange_fill_id="ex-fill-002")

    assert derive_position_id(first_fill) == derive_position_id(second_fill)


def test_additional_buy_uses_weighted_average_cost() -> None:
    first = apply_fill_to_position(None, _fill(price="0.40", quantity="10"), currency="USD")

    second = apply_fill_to_position(
        first.position,
        _fill(
            fill_id="fill_additional_buy",
            exchange_fill_id="ex-fill-002",
            price="0.70",
            quantity="5",
            exchange_occurred_at=OCCURRED_AT + timedelta(seconds=2),
            received_at=RECEIVED_AT + timedelta(seconds=2),
        ),
        currency="USD",
    )

    assert second.position.quantity == Decimal("15")
    assert second.position.average_entry_price == Decimal("0.50")
    assert second.position.realized_pnl == _money("0")
    assert second.position.aggregate_version == 2
    assert second.trade_notional == _money("3.50")
    assert second.closed_quantity == Decimal("0")
    assert second.opened_quantity == Decimal("5")
    assert second.closed_cost_basis == _money("0")
    assert second.closed_trade_value == _money("0")
    assert second.opened_notional == _money("3.50")


def test_partial_sell_reduces_long_position_and_realizes_pnl() -> None:
    first = apply_fill_to_position(None, _fill(price="0.40", quantity="10"), currency="USD")

    second = apply_fill_to_position(
        first.position,
        _fill(
            fill_id="fill_partial_sell",
            exchange_fill_id="ex-fill-002",
            side=Side.SELL,
            price="0.60",
            quantity="4",
        ),
        currency="USD",
    )

    assert second.position.quantity == Decimal("6")
    assert second.position.average_entry_price == Decimal("0.40")
    assert second.realized_trading_pnl == _money("0.80")
    assert second.position.realized_pnl == _money("0.80")
    assert second.trade_notional == _money("2.40")
    assert second.closed_quantity == Decimal("4")
    assert second.opened_quantity == Decimal("0")
    assert second.closed_cost_basis == _money("1.60")
    assert second.closed_trade_value == _money("2.40")
    assert second.opened_notional == _money("0")


def test_full_close_clears_average_and_open_timestamp() -> None:
    first = apply_fill_to_position(None, _fill(price="0.40", quantity="10"), currency="USD")

    second = apply_fill_to_position(
        first.position,
        _fill(
            fill_id="fill_full_close",
            exchange_fill_id="ex-fill-002",
            side=Side.SELL,
            price="0.45",
            quantity="10",
        ),
        currency="USD",
    )

    assert second.position.quantity == Decimal("0")
    assert second.position.average_entry_price is None
    assert second.position.opened_at is None
    assert second.realized_trading_pnl == _money("0.50")
    assert second.position.realized_pnl == _money("0.50")
    assert second.trade_notional == _money("4.50")
    assert second.closed_quantity == Decimal("10")
    assert second.opened_quantity == Decimal("0")
    assert second.closed_cost_basis == _money("4.00")
    assert second.closed_trade_value == _money("4.50")
    assert second.opened_notional == _money("0")


def test_reversal_closes_existing_position_and_opens_new_direction() -> None:
    first = apply_fill_to_position(None, _fill(price="0.40", quantity="10"), currency="USD")
    reversal_time = OCCURRED_AT + timedelta(minutes=1)

    second = apply_fill_to_position(
        first.position,
        _fill(
            fill_id="fill_reversal",
            exchange_fill_id="ex-fill-002",
            side=Side.SELL,
            price="0.50",
            quantity="15",
            exchange_occurred_at=reversal_time,
            received_at=reversal_time + timedelta(seconds=1),
        ),
        currency="USD",
    )

    assert second.position.quantity == Decimal("-5")
    assert second.position.average_entry_price == Decimal("0.50")
    assert second.position.opened_at == reversal_time
    assert second.realized_trading_pnl == _money("1.00")
    assert second.position.realized_pnl == _money("1.00")
    assert second.trade_notional == _money("7.50")
    assert second.closed_quantity == Decimal("10")
    assert second.opened_quantity == Decimal("5")
    assert second.closed_cost_basis == _money("4.00")
    assert second.closed_trade_value == _money("5.00")
    assert second.opened_notional == _money("2.50")


def test_partial_buy_reduces_short_position_and_realizes_pnl() -> None:
    first = apply_fill_to_position(
        None,
        _fill(side=Side.SELL, price="0.70", quantity="10"),
        currency="USD",
    )

    second = apply_fill_to_position(
        first.position,
        _fill(
            fill_id="fill_short_cover",
            exchange_fill_id="ex-fill-002",
            side=Side.BUY,
            price="0.40",
            quantity="4",
        ),
        currency="USD",
    )

    assert second.position.quantity == Decimal("-6")
    assert second.position.average_entry_price == Decimal("0.70")
    assert second.realized_trading_pnl == _money("1.20")
    assert second.position.realized_pnl == _money("1.20")
    assert second.trade_notional == _money("1.60")
    assert second.closed_quantity == Decimal("4")
    assert second.opened_quantity == Decimal("0")
    assert second.closed_cost_basis == _money("2.80")
    assert second.closed_trade_value == _money("1.60")
    assert second.opened_notional == _money("0")


def test_fees_and_rebates_accumulate_without_changing_realized_trading_pnl() -> None:
    first = apply_fill_to_position(
        None,
        _fill(price="0.40", quantity="10", fee=_money("0.02"), rebate=_money("0.01")),
        currency="USD",
    )

    second = apply_fill_to_position(
        first.position,
        _fill(
            fill_id="fill_fee_rebate",
            exchange_fill_id="ex-fill-002",
            price="0.41",
            quantity="1",
            fee=_money("0.03"),
            rebate=_money("0.04"),
        ),
        currency="USD",
    )

    assert second.position.realized_pnl == _money("0")
    assert second.position.fees_paid == _money("0.05")
    assert second.position.rebates_received == _money("0.05")
    assert second.fee == _money("0.03")
    assert second.rebate == _money("0.04")


def test_projection_rejects_fee_currency_mismatch() -> None:
    with pytest.raises(PortfolioProjectionError, match="fee currency"):
        apply_fill_to_position(None, _fill(fee=_money("0.01", currency="EUR")), currency="USD")


def test_projection_rejects_existing_position_identity_mismatch() -> None:
    position = apply_fill_to_position(
        None,
        _fill(price="0.40", quantity="10"),
        currency="USD",
    ).position

    with pytest.raises(PortfolioProjectionError, match="contract_id"):
        apply_fill_to_position(
            position,
            _fill(contract_id="ctr_other_contract"),
            currency="USD",
        )


def test_projection_rejects_nonzero_position_without_average_entry_price() -> None:
    position = _position(quantity="1", average_entry_price=None)

    with pytest.raises(PortfolioProjectionError, match="requires average_entry_price"):
        apply_fill_to_position(position, _fill(), currency="USD")


def test_projection_resets_stale_unrealized_pnl_until_mark_policy_runs() -> None:
    position = _position(unrealized_pnl=_money("5.00"))

    result = apply_fill_to_position(position, _fill(price="0.50", quantity="2"), currency="USD")

    assert result.position.unrealized_pnl == _money("0")


def test_projection_rejects_fill_older_than_position_update_horizon() -> None:
    position = _position()

    with pytest.raises(PortfolioProjectionError, match="older than the position update horizon"):
        apply_fill_to_position(
            position,
            _fill(
                fill_id="fill_stale_001",
                exchange_fill_id="ex-fill-stale-001",
                exchange_occurred_at=OCCURRED_AT - timedelta(seconds=1),
                received_at=RECEIVED_AT + timedelta(seconds=30),
            ),
            currency="USD",
        )


def _fill(
    *,
    fill_id: str = "fill_test_001",
    exchange_fill_id: str = "ex-fill-001",
    order_id: str = "ord_order_001",
    exchange_order_id: str | None = "exchange-order-001",
    client_order_id: str = "client-order-001",
    exchange: str = "kalshi",
    account_id: str = "acct_paper_001",
    market_id: str = "mkt_market_001",
    contract_id: str = "ctr_contract_001",
    outcome_id: str = "out_yes",
    side: Side = Side.BUY,
    price: str = "0.40",
    quantity: str = "10",
    liquidity_role: LiquidityRole = LiquidityRole.MAKER,
    fee: Money | None = None,
    rebate: Money | None = None,
    exchange_occurred_at: datetime = OCCURRED_AT,
    received_at: datetime = RECEIVED_AT,
    trade_id: str | None = "trade-001",
) -> Fill:
    return Fill(
        fill_id=fill_id,
        exchange_fill_id=exchange_fill_id,
        order_id=order_id,
        exchange_order_id=exchange_order_id,
        client_order_id=client_order_id,
        exchange=exchange,
        account_id=account_id,
        market_id=market_id,
        contract_id=contract_id,
        outcome_id=outcome_id,
        side=side,
        price=price,
        quantity=quantity,
        liquidity_role=liquidity_role,
        fee=fee,
        rebate=rebate,
        exchange_occurred_at=exchange_occurred_at,
        received_at=received_at,
        trade_id=trade_id,
    )


def _position(
    *,
    quantity: str = "3",
    average_entry_price: str | None = "0.40",
    realized_pnl: Money | None = None,
    unrealized_pnl: Money | None = None,
    fees_paid: Money | None = None,
    rebates_received: Money | None = None,
) -> Position:
    return Position(
        position_id="pos_existing_001",
        exchange="kalshi",
        account_id="acct_paper_001",
        market_id="mkt_market_001",
        contract_id="ctr_contract_001",
        outcome_id="out_yes",
        quantity=quantity,
        average_entry_price=average_entry_price,
        realized_pnl=realized_pnl or _money("0"),
        unrealized_pnl=unrealized_pnl or _money("0"),
        fees_paid=fees_paid or _money("0"),
        rebates_received=rebates_received or _money("0"),
        opened_at=OCCURRED_AT,
        last_updated_at=OCCURRED_AT,
        aggregate_version=3,
    )


def _money(amount: str, *, currency: str = "USD") -> Money:
    return Money(amount=Decimal(amount), currency=currency)
