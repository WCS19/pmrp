"""Deterministic fill models for simulated limit orders."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, runtime_checkable

from pmrp.schemas.enums import LiquidityRole, Side
from pmrp.schemas.market_data import OrderBookLevel, OrderBookSnapshot
from pmrp.schemas.numeric import parse_decimal
from pmrp.simulation.errors import SimulationInputError

TOUCH_FILL_MODEL_NAME = "touch_fill_v1"
TRADE_THROUGH_FILL_MODEL_NAME = "trade_through_v1"

_ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class SimulatedFillComponent:
    """One simulated execution component at one book price level."""

    price: Decimal
    quantity: Decimal
    liquidity_role: LiquidityRole


@dataclass(frozen=True, slots=True)
class FillEstimate:
    """Deterministic estimated fill outcome for one simulated order."""

    side: Side
    limit_price: Decimal
    order_quantity: Decimal
    filled_quantity: Decimal
    remaining_quantity: Decimal
    average_fill_price: Decimal | None
    liquidity_role: LiquidityRole
    components: tuple[SimulatedFillComponent, ...]
    reason_code: str

    @property
    def has_fill(self) -> bool:
        """Return whether any simulated quantity filled."""

        return self.filled_quantity > _ZERO

    @property
    def is_partial(self) -> bool:
        """Return whether the estimate filled some but not all order quantity."""

        return _ZERO < self.filled_quantity < self.order_quantity

    @property
    def is_full(self) -> bool:
        """Return whether the estimate filled the full order quantity."""

        return self.filled_quantity == self.order_quantity


@runtime_checkable
class FillModel(Protocol):
    """Pure fill model for simulated limit orders."""

    def evaluate(
        self,
        *,
        snapshot: OrderBookSnapshot,
        side: Side,
        limit_price: Decimal,
        quantity: Decimal,
    ) -> FillEstimate:
        """Estimate simulated fills from displayed book depth."""
        ...


class TouchFillModel:
    """Fill marketable limit orders against visible depth at touch or better."""

    def evaluate(
        self,
        *,
        snapshot: OrderBookSnapshot,
        side: Side,
        limit_price: Decimal,
        quantity: Decimal,
    ) -> FillEstimate:
        """Return the deterministic taker fill estimate at executable prices."""

        return _estimate_book_fill(
            snapshot=snapshot,
            side=side,
            limit_price=limit_price,
            quantity=quantity,
            allow_touch=True,
            reason_prefix="simulation_touch",
        )


class TradeThroughFillModel:
    """Fill only when visible depth trades strictly through the limit price."""

    def evaluate(
        self,
        *,
        snapshot: OrderBookSnapshot,
        side: Side,
        limit_price: Decimal,
        quantity: Decimal,
    ) -> FillEstimate:
        """Return the deterministic taker fill estimate for strict trade-throughs."""

        return _estimate_book_fill(
            snapshot=snapshot,
            side=side,
            limit_price=limit_price,
            quantity=quantity,
            allow_touch=False,
            reason_prefix="simulation_trade_through",
        )


def _estimate_book_fill(
    *,
    snapshot: OrderBookSnapshot,
    side: Side,
    limit_price: Decimal,
    quantity: Decimal,
    allow_touch: bool,
    reason_prefix: str,
) -> FillEstimate:
    side, limit_price, quantity = _validate_inputs(
        snapshot=snapshot,
        side=side,
        limit_price=limit_price,
        quantity=quantity,
    )

    remaining = quantity
    components: list[SimulatedFillComponent] = []
    for level in _opposite_side_levels(snapshot=snapshot, side=side):
        if remaining == _ZERO or not _is_executable(
            side=side,
            limit_price=limit_price,
            level_price=level.price,
            allow_touch=allow_touch,
        ):
            break
        fill_quantity = min(remaining, level.quantity)
        if fill_quantity == _ZERO:
            continue
        components.append(
            SimulatedFillComponent(
                price=level.price,
                quantity=fill_quantity,
                liquidity_role=LiquidityRole.TAKER,
            )
        )
        remaining -= fill_quantity

    filled_quantity = quantity - remaining
    return FillEstimate(
        side=side,
        limit_price=limit_price,
        order_quantity=quantity,
        filled_quantity=filled_quantity,
        remaining_quantity=remaining,
        average_fill_price=_average_fill_price(components),
        liquidity_role=LiquidityRole.TAKER if components else LiquidityRole.UNKNOWN,
        components=tuple(components),
        reason_code=_reason_code(
            reason_prefix=reason_prefix, filled=filled_quantity, total=quantity
        ),
    )


def _validate_inputs(
    *,
    snapshot: OrderBookSnapshot,
    side: Side,
    limit_price: Decimal,
    quantity: Decimal,
) -> tuple[Side, Decimal, Decimal]:
    if not isinstance(snapshot, OrderBookSnapshot):
        raise SimulationInputError(
            "Fill model requires an OrderBookSnapshot",
            reason_code="simulation_fill_snapshot_invalid",
        )
    if not snapshot.is_valid:
        raise SimulationInputError(
            "Fill model requires a valid order book snapshot",
            reason_code="simulation_fill_snapshot_invalid",
            context={"market_id": str(snapshot.market_id)},
        )
    if not isinstance(side, Side):
        raise SimulationInputError(
            "Fill model side must be a canonical Side",
            reason_code="simulation_fill_side_invalid",
        )

    parsed_limit_price = parse_decimal(limit_price, field_name="fill model limit_price")
    parsed_quantity = parse_decimal(quantity, field_name="fill model quantity")
    if parsed_limit_price < _ZERO:
        msg = "fill model limit_price must be nonnegative"
        raise ValueError(msg)
    if parsed_quantity <= _ZERO:
        msg = "fill model quantity must be positive"
        raise ValueError(msg)
    return side, parsed_limit_price, parsed_quantity


def _opposite_side_levels(
    *,
    snapshot: OrderBookSnapshot,
    side: Side,
) -> tuple[OrderBookLevel, ...]:
    if side is Side.BUY:
        return snapshot.asks
    return snapshot.bids


def _is_executable(
    *,
    side: Side,
    limit_price: Decimal,
    level_price: Decimal,
    allow_touch: bool,
) -> bool:
    if side is Side.BUY:
        return level_price <= limit_price if allow_touch else level_price < limit_price
    return level_price >= limit_price if allow_touch else level_price > limit_price


def _average_fill_price(components: list[SimulatedFillComponent]) -> Decimal | None:
    filled_quantity = sum((component.quantity for component in components), _ZERO)
    if filled_quantity == _ZERO:
        return None
    notional = sum((component.price * component.quantity for component in components), _ZERO)
    return notional / filled_quantity


def _reason_code(*, reason_prefix: str, filled: Decimal, total: Decimal) -> str:
    if filled == _ZERO:
        return f"{reason_prefix}_no_fill"
    if filled < total:
        return f"{reason_prefix}_partial_fill"
    return f"{reason_prefix}_full_fill"
