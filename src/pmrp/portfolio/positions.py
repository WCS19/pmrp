"""Position projection helpers for portfolio accounting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Final

from pmrp.portfolio.errors import PortfolioProjectionError
from pmrp.schemas.enums import Side
from pmrp.schemas.identifiers import PositionId
from pmrp.schemas.numeric import Money, validate_currency
from pmrp.schemas.orders import Fill
from pmrp.schemas.portfolio import Position
from pmrp.schemas.serialization import canonical_sha256

WEIGHTED_AVERAGE_COST_METHOD: Final = "weighted_average_cost_v1"
UNREALIZED_PNL_POLICY: Final = "reset_to_zero_pending_mark_v1"

_ZERO = Decimal("0")
_ONE = Decimal("1")
_NEGATIVE_ONE = Decimal("-1")


@dataclass(frozen=True, slots=True)
class PositionProjectionResult:
    """Result of applying one fill to one canonical position projection."""

    position: Position
    realized_trading_pnl: Money
    fee: Money
    rebate: Money
    trade_notional: Money
    closed_quantity: Decimal
    opened_quantity: Decimal
    closed_cost_basis: Money
    closed_trade_value: Money
    opened_notional: Money
    accounting_method: str = WEIGHTED_AVERAGE_COST_METHOD
    unrealized_pnl_policy: str = UNREALIZED_PNL_POLICY


@dataclass(frozen=True, slots=True)
class _WeightedAverageProjection:
    quantity: Decimal
    average_entry_price: Decimal | None
    realized_trading_pnl: Decimal
    closed_quantity: Decimal
    opened_quantity: Decimal
    closed_cost_basis: Decimal
    closed_trade_value: Decimal
    opened_notional: Decimal


def apply_fill_to_position(
    position: Position | None,
    fill: Fill,
    *,
    currency: str,
    position_id: PositionId | None = None,
) -> PositionProjectionResult:
    """Apply one canonical fill to a position using weighted-average cost.

    The projection updates position quantity, average entry price, cumulative
    realized trading PnL, and cumulative fee/rebate totals. Unrealized PnL is
    reset to zero because this fill-only projection does not have a mark price.
    Fills must be applied in nondecreasing ``exchange_occurred_at`` order; this
    helper stores the latest applied fill exchange timestamp in
    ``Position.last_updated_at`` and rejects older fills.
    Duplicate-fill idempotency is handled by the journal or repository layer.
    """

    validated_currency = validate_currency(currency)
    fee = _fill_money(fill.fee, currency=validated_currency, field_name="fee")
    rebate = _fill_money(fill.rebate, currency=validated_currency, field_name="rebate")

    if position is None:
        resolved_position_id = position_id or derive_position_id(fill)
        existing_quantity = _ZERO
        existing_average: Decimal | None = None
        existing_realized = _zero_money(validated_currency)
        existing_fees = _zero_money(validated_currency)
        existing_rebates = _zero_money(validated_currency)
        existing_opened_at = None
        existing_last_updated_at = None
        existing_version = 0
    else:
        _validate_existing_position(
            position,
            fill,
            currency=validated_currency,
            position_id=position_id,
        )
        resolved_position_id = position.position_id
        existing_quantity = position.quantity
        existing_average = position.average_entry_price
        existing_realized = position.realized_pnl
        existing_fees = position.fees_paid
        existing_rebates = position.rebates_received
        existing_opened_at = position.opened_at
        existing_last_updated_at = position.last_updated_at
        existing_version = position.aggregate_version
        _validate_fill_order(
            existing_last_updated_at=existing_last_updated_at,
            fill=fill,
        )

    projection = _apply_weighted_average_fill(
        existing_quantity=existing_quantity,
        existing_average=existing_average,
        fill=fill,
    )

    opened_at = _project_opened_at(
        existing_quantity=existing_quantity,
        projected_quantity=projection.quantity,
        existing_opened_at=existing_opened_at,
        fill=fill,
    )
    updated_at = _project_updated_at(existing_last_updated_at, fill)

    projected_position = Position(
        position_id=resolved_position_id,
        exchange=fill.exchange,
        account_id=fill.account_id,
        market_id=fill.market_id,
        contract_id=fill.contract_id,
        outcome_id=fill.outcome_id,
        quantity=projection.quantity,
        average_entry_price=projection.average_entry_price,
        realized_pnl=Money(
            amount=existing_realized.amount + projection.realized_trading_pnl,
            currency=validated_currency,
        ),
        unrealized_pnl=_zero_money(validated_currency),
        fees_paid=Money(
            amount=existing_fees.amount + fee.amount,
            currency=validated_currency,
        ),
        rebates_received=Money(
            amount=existing_rebates.amount + rebate.amount,
            currency=validated_currency,
        ),
        opened_at=opened_at,
        last_updated_at=updated_at,
        aggregate_version=existing_version + 1,
    )
    return PositionProjectionResult(
        position=projected_position,
        realized_trading_pnl=Money(
            amount=projection.realized_trading_pnl,
            currency=validated_currency,
        ),
        fee=fee,
        rebate=rebate,
        trade_notional=Money(
            amount=fill.quantity * fill.price,
            currency=validated_currency,
        ),
        closed_quantity=projection.closed_quantity,
        opened_quantity=projection.opened_quantity,
        closed_cost_basis=Money(
            amount=projection.closed_cost_basis,
            currency=validated_currency,
        ),
        closed_trade_value=Money(
            amount=projection.closed_trade_value,
            currency=validated_currency,
        ),
        opened_notional=Money(
            amount=projection.opened_notional,
            currency=validated_currency,
        ),
    )


def derive_position_id(fill: Fill) -> PositionId:
    """Derive a stable position identifier from the account and contract identity."""

    digest = canonical_sha256(
        {
            "account_id": fill.account_id,
            "contract_id": fill.contract_id,
            "exchange": fill.exchange,
            "market_id": fill.market_id,
            "outcome_id": fill.outcome_id,
            "schema": "pmrp.position_identity.v1",
        }
    ).removeprefix("sha256:")
    return PositionId(f"pos_{digest[:32]}")


def _apply_weighted_average_fill(
    *,
    existing_quantity: Decimal,
    existing_average: Decimal | None,
    fill: Fill,
) -> _WeightedAverageProjection:
    fill_quantity = _signed_fill_quantity(fill)
    projected_quantity = existing_quantity + fill_quantity

    if existing_quantity == _ZERO:
        opened_quantity = abs(fill_quantity)
        return _WeightedAverageProjection(
            quantity=projected_quantity,
            average_entry_price=fill.price,
            realized_trading_pnl=_ZERO,
            closed_quantity=_ZERO,
            opened_quantity=opened_quantity,
            closed_cost_basis=_ZERO,
            closed_trade_value=_ZERO,
            opened_notional=opened_quantity * fill.price,
        )

    if existing_average is None:
        msg = "nonzero existing position requires average_entry_price"
        raise PortfolioProjectionError(msg)

    if _same_direction(existing_quantity, fill_quantity):
        projected_average = (
            (abs(existing_quantity) * existing_average) + (abs(fill_quantity) * fill.price)
        ) / abs(projected_quantity)
        opened_quantity = abs(fill_quantity)
        return _WeightedAverageProjection(
            quantity=projected_quantity,
            average_entry_price=projected_average,
            realized_trading_pnl=_ZERO,
            closed_quantity=_ZERO,
            opened_quantity=opened_quantity,
            closed_cost_basis=_ZERO,
            closed_trade_value=_ZERO,
            opened_notional=opened_quantity * fill.price,
        )

    closed_quantity = min(abs(existing_quantity), abs(fill_quantity))
    realized_increment = (
        closed_quantity * (fill.price - existing_average) * _sign(existing_quantity)
    )
    opened_quantity = max(abs(fill_quantity) - abs(existing_quantity), _ZERO)
    closed_cost_basis = closed_quantity * existing_average
    closed_trade_value = closed_quantity * fill.price
    opened_notional = opened_quantity * fill.price

    if projected_quantity == _ZERO:
        return _WeightedAverageProjection(
            quantity=projected_quantity,
            average_entry_price=None,
            realized_trading_pnl=realized_increment,
            closed_quantity=closed_quantity,
            opened_quantity=opened_quantity,
            closed_cost_basis=closed_cost_basis,
            closed_trade_value=closed_trade_value,
            opened_notional=opened_notional,
        )
    if _same_direction(existing_quantity, projected_quantity):
        return _WeightedAverageProjection(
            quantity=projected_quantity,
            average_entry_price=existing_average,
            realized_trading_pnl=realized_increment,
            closed_quantity=closed_quantity,
            opened_quantity=opened_quantity,
            closed_cost_basis=closed_cost_basis,
            closed_trade_value=closed_trade_value,
            opened_notional=opened_notional,
        )
    return _WeightedAverageProjection(
        quantity=projected_quantity,
        average_entry_price=fill.price,
        realized_trading_pnl=realized_increment,
        closed_quantity=closed_quantity,
        opened_quantity=opened_quantity,
        closed_cost_basis=closed_cost_basis,
        closed_trade_value=closed_trade_value,
        opened_notional=opened_notional,
    )


def _fill_money(
    money: Money | None,
    *,
    currency: str,
    field_name: str,
) -> Money:
    if money is None:
        return _zero_money(currency)
    _validate_money(money, currency=currency, field_name=field_name)
    if money.amount < _ZERO:
        msg = f"{field_name} amount must be nonnegative"
        raise PortfolioProjectionError(msg)
    return money


def _validate_existing_position(
    position: Position,
    fill: Fill,
    *,
    currency: str,
    position_id: PositionId | None,
) -> None:
    if position_id is not None and position.position_id != position_id:
        msg = "position_id does not match existing position"
        raise PortfolioProjectionError(msg)
    if position.exchange != fill.exchange:
        msg = "fill exchange does not match position exchange"
        raise PortfolioProjectionError(msg)
    if position.account_id != fill.account_id:
        msg = "fill account_id does not match position account_id"
        raise PortfolioProjectionError(msg)
    if position.market_id != fill.market_id:
        msg = "fill market_id does not match position market_id"
        raise PortfolioProjectionError(msg)
    if position.contract_id != fill.contract_id:
        msg = "fill contract_id does not match position contract_id"
        raise PortfolioProjectionError(msg)
    if position.outcome_id != fill.outcome_id:
        msg = "fill outcome_id does not match position outcome_id"
        raise PortfolioProjectionError(msg)
    if position.quantity == _ZERO and position.average_entry_price is not None:
        msg = "flat existing position must not have average_entry_price"
        raise PortfolioProjectionError(msg)
    if position.quantity != _ZERO and position.average_entry_price is None:
        msg = "nonzero existing position requires average_entry_price"
        raise PortfolioProjectionError(msg)

    _validate_money(position.realized_pnl, currency=currency, field_name="realized_pnl")
    _validate_money(position.unrealized_pnl, currency=currency, field_name="unrealized_pnl")
    _validate_money(position.fees_paid, currency=currency, field_name="fees_paid")
    _validate_money(position.rebates_received, currency=currency, field_name="rebates_received")


def _validate_money(money: Money, *, currency: str, field_name: str) -> None:
    if money.currency != currency:
        msg = f"{field_name} currency must match projection currency"
        raise PortfolioProjectionError(msg)


def _project_opened_at(
    *,
    existing_quantity: Decimal,
    projected_quantity: Decimal,
    existing_opened_at: datetime | None,
    fill: Fill,
) -> datetime | None:
    if projected_quantity == _ZERO:
        return None
    if existing_quantity == _ZERO or existing_opened_at is None:
        return fill.exchange_occurred_at
    if _same_direction(existing_quantity, projected_quantity):
        return min(existing_opened_at, fill.exchange_occurred_at)
    return fill.exchange_occurred_at


def _validate_fill_order(*, existing_last_updated_at: datetime, fill: Fill) -> None:
    if fill.exchange_occurred_at < existing_last_updated_at:
        msg = "fill exchange_occurred_at is older than the position update horizon"
        raise PortfolioProjectionError(msg)


def _project_updated_at(existing_last_updated_at: datetime | None, fill: Fill) -> datetime:
    if existing_last_updated_at is None:
        return fill.exchange_occurred_at
    return max(existing_last_updated_at, fill.exchange_occurred_at)


def _signed_fill_quantity(fill: Fill) -> Decimal:
    if fill.side == Side.BUY:
        return fill.quantity
    return -fill.quantity


def _same_direction(left: Decimal, right: Decimal) -> bool:
    return _sign(left) == _sign(right)


def _sign(value: Decimal) -> Decimal:
    if value > _ZERO:
        return _ONE
    if value < _ZERO:
        return _NEGATIVE_ONE
    msg = "zero does not have a position direction"
    raise PortfolioProjectionError(msg)


def _zero_money(currency: str) -> Money:
    return Money(amount=_ZERO, currency=currency)
