"""Accounting journal construction for portfolio fills."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Final

from pmrp.portfolio.errors import PortfolioProjectionError
from pmrp.portfolio.positions import PositionProjectionResult
from pmrp.schemas.enums import Side
from pmrp.schemas.identifiers import EventId
from pmrp.schemas.numeric import Money
from pmrp.schemas.orders import Fill
from pmrp.schemas.portfolio import AccountingJournalEntry, JournalLine
from pmrp.schemas.serialization import canonical_sha256

ACCOUNT_CASH: Final = "cash"
ACCOUNT_POSITION_COST: Final = "position_cost"
ACCOUNT_REALIZED_TRADING_PNL: Final = "realized_trading_pnl"
ACCOUNT_FEES_PAID: Final = "fees_paid"
ACCOUNT_REBATES_RECEIVED: Final = "rebates_received"
FILL_REFERENCE_TYPE: Final = "fill"

_ZERO = Decimal("0")
_ONE = Decimal("1")
_NEGATIVE_ONE = Decimal("-1")


def build_fill_journal_entry(
    *,
    fill: Fill,
    projection: PositionProjectionResult,
    source_event_id: EventId,
    created_at: datetime,
) -> AccountingJournalEntry:
    """Build a balanced accounting journal entry for one fill projection.

    Positive realized trading PnL is represented as a negative journal line so
    the economic PnL amount can balance against cash and position-cost movement.
    """

    _validate_projection_for_fill(fill, projection)
    currency = projection.trade_notional.currency
    fill_direction = _fill_direction(fill)
    closed_position_direction = -fill_direction

    lines = [
        JournalLine(
            account_code=ACCOUNT_CASH,
            amount=-fill_direction * projection.trade_notional.amount,
            currency=currency,
            description="Trade cash movement.",
        )
    ]

    if projection.closed_quantity > _ZERO:
        lines.append(
            JournalLine(
                account_code=ACCOUNT_POSITION_COST,
                amount=-(closed_position_direction * projection.closed_cost_basis.amount),
                currency=currency,
                description="Closed position cost basis.",
            )
        )
        lines.append(
            JournalLine(
                account_code=ACCOUNT_REALIZED_TRADING_PNL,
                amount=-projection.realized_trading_pnl.amount,
                currency=currency,
                description="Realized trading PnL offset.",
            )
        )

    if projection.opened_quantity > _ZERO:
        lines.append(
            JournalLine(
                account_code=ACCOUNT_POSITION_COST,
                amount=fill_direction * projection.opened_notional.amount,
                currency=currency,
                description="Opened position notional.",
            )
        )

    if projection.fee.amount > _ZERO:
        lines.extend(
            (
                JournalLine(
                    account_code=ACCOUNT_CASH,
                    amount=-projection.fee.amount,
                    currency=currency,
                    description="Fee cash movement.",
                ),
                JournalLine(
                    account_code=ACCOUNT_FEES_PAID,
                    amount=projection.fee.amount,
                    currency=currency,
                    description="Fee expense.",
                ),
            )
        )

    if projection.rebate.amount > _ZERO:
        lines.extend(
            (
                JournalLine(
                    account_code=ACCOUNT_CASH,
                    amount=projection.rebate.amount,
                    currency=currency,
                    description="Rebate cash movement.",
                ),
                JournalLine(
                    account_code=ACCOUNT_REBATES_RECEIVED,
                    amount=-projection.rebate.amount,
                    currency=currency,
                    description="Rebate income.",
                ),
            )
        )

    return AccountingJournalEntry(
        journal_entry_id=derive_fill_journal_entry_id(fill),
        occurred_at=fill.exchange_occurred_at,
        source_event_id=source_event_id,
        reference_type=FILL_REFERENCE_TYPE,
        reference_id=fill.fill_id,
        lines=tuple(lines),
        description=f"Fill accounting for {fill.fill_id}.",
        created_at=created_at,
    )


def derive_fill_journal_entry_id(fill: Fill) -> str:
    """Derive a stable journal entry identifier from the canonical fill ID."""

    digest = canonical_sha256(
        {
            "fill_id": fill.fill_id,
            "schema": "pmrp.fill_journal_entry.v1",
        }
    ).removeprefix("sha256:")
    return f"journal_fill_{digest[:32]}"


def _validate_projection_for_fill(fill: Fill, projection: PositionProjectionResult) -> None:
    expected_trade_notional = fill.quantity * fill.price
    currency = projection.trade_notional.currency

    if projection.position.exchange != fill.exchange:
        msg = "projection position exchange does not match fill exchange"
        raise PortfolioProjectionError(msg)
    if projection.position.account_id != fill.account_id:
        msg = "projection position account_id does not match fill account_id"
        raise PortfolioProjectionError(msg)
    if projection.position.market_id != fill.market_id:
        msg = "projection position market_id does not match fill market_id"
        raise PortfolioProjectionError(msg)
    if projection.position.contract_id != fill.contract_id:
        msg = "projection position contract_id does not match fill contract_id"
        raise PortfolioProjectionError(msg)
    if projection.position.outcome_id != fill.outcome_id:
        msg = "projection position outcome_id does not match fill outcome_id"
        raise PortfolioProjectionError(msg)

    _validate_money(projection.realized_trading_pnl, currency, "realized_trading_pnl")
    _validate_money(projection.fee, currency, "fee")
    _validate_money(projection.rebate, currency, "rebate")
    _validate_money(projection.closed_cost_basis, currency, "closed_cost_basis")
    _validate_money(projection.closed_trade_value, currency, "closed_trade_value")
    _validate_money(projection.opened_notional, currency, "opened_notional")
    _validate_nonnegative_money(projection.trade_notional, "trade_notional")
    _validate_nonnegative_money(projection.fee, "fee")
    _validate_nonnegative_money(projection.rebate, "rebate")
    _validate_nonnegative_money(projection.closed_cost_basis, "closed_cost_basis")
    _validate_nonnegative_money(projection.closed_trade_value, "closed_trade_value")
    _validate_nonnegative_money(projection.opened_notional, "opened_notional")

    if projection.trade_notional.amount != expected_trade_notional:
        msg = "projection trade_notional does not match fill notional"
        raise PortfolioProjectionError(msg)
    if projection.fee != _fill_money(fill.fee, currency):
        msg = "projection fee does not match fill fee"
        raise PortfolioProjectionError(msg)
    if projection.rebate != _fill_money(fill.rebate, currency):
        msg = "projection rebate does not match fill rebate"
        raise PortfolioProjectionError(msg)
    if projection.closed_quantity < _ZERO or projection.opened_quantity < _ZERO:
        msg = "projection closed and opened quantities must be nonnegative"
        raise PortfolioProjectionError(msg)
    if projection.closed_quantity + projection.opened_quantity != fill.quantity:
        msg = "projection closed and opened quantities must equal fill quantity"
        raise PortfolioProjectionError(msg)
    if projection.closed_trade_value.amount != projection.closed_quantity * fill.price:
        msg = "projection closed_trade_value does not match fill price"
        raise PortfolioProjectionError(msg)
    if projection.opened_notional.amount != projection.opened_quantity * fill.price:
        msg = "projection opened_notional does not match fill price"
        raise PortfolioProjectionError(msg)

    expected_realized = (
        projection.closed_trade_value.amount - projection.closed_cost_basis.amount
    ) * (-_fill_direction(fill))
    if projection.realized_trading_pnl.amount != expected_realized:
        msg = "projection realized_trading_pnl does not match closed cost basis"
        raise PortfolioProjectionError(msg)


def _validate_money(money: Money, currency: str, field_name: str) -> None:
    if money.currency != currency:
        msg = f"projection {field_name} currency does not match trade_notional currency"
        raise PortfolioProjectionError(msg)


def _validate_nonnegative_money(money: Money, field_name: str) -> None:
    if money.amount < _ZERO:
        msg = f"projection {field_name} amount must be nonnegative"
        raise PortfolioProjectionError(msg)


def _fill_money(money: Money | None, currency: str) -> Money:
    if money is None:
        return Money(amount=_ZERO, currency=currency)
    return money


def _fill_direction(fill: Fill) -> Decimal:
    if fill.side == Side.BUY:
        return _ONE
    return _NEGATIVE_ONE
