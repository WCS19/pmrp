"""Deterministic slippage models for simulated fill prices."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, localcontext
from typing import Protocol, runtime_checkable

from pmrp.schemas.enums import LiquidityRole, Side
from pmrp.schemas.numeric import parse_decimal
from pmrp.schemas.simulation import SimulationConfiguration
from pmrp.simulation.errors import SimulationConfigurationError, SimulationInputError

BPS_SLIPPAGE_MODEL_NAME = "bps_slippage_v1"
NO_SLIPPAGE_MODEL_NAME = "none_v1"

_BASIS_POINTS_DENOMINATOR = Decimal("10000")
_MAX_DECIMAL_ADJUSTED_EXPONENT = 36
_MAX_DECIMAL_DIGITS = 28
_MAX_DECIMAL_SCALE = 18
_SLIPPAGE_ARITHMETIC_CONTEXT = Context(prec=128)
_ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class SlippageEstimate:
    """Estimated simulated slippage for one fill component."""

    side: Side
    liquidity_role: LiquidityRole
    input_price: Decimal
    adjusted_price: Decimal
    quantity: Decimal
    slippage_bps: Decimal
    slippage_amount_per_unit: Decimal
    total_slippage: Decimal


@runtime_checkable
class SlippageModel(Protocol):
    """Pure slippage model for simulated fill prices."""

    def estimate(
        self,
        *,
        side: Side,
        price: Decimal,
        quantity: Decimal,
        liquidity_role: LiquidityRole,
    ) -> SlippageEstimate:
        """Estimate simulated slippage for one fill component."""
        ...


class NoSlippageModel:
    """Return fill prices unchanged."""

    @classmethod
    def from_configuration(cls, configuration: SimulationConfiguration) -> NoSlippageModel:
        """Create a no-slippage model from canonical simulation configuration."""

        if configuration.slippage_model != NO_SLIPPAGE_MODEL_NAME:
            raise SimulationConfigurationError(
                "Simulation slippage_model must select the no-slippage model",
                reason_code="simulation_slippage_model_unsupported",
                context={"slippage_model": configuration.slippage_model},
            )
        return cls()

    def estimate(
        self,
        *,
        side: Side,
        price: Decimal,
        quantity: Decimal,
        liquidity_role: LiquidityRole,
    ) -> SlippageEstimate:
        """Return a zero-slippage estimate."""

        side, price, quantity, liquidity_role = _validate_inputs(
            side=side,
            price=price,
            quantity=quantity,
            liquidity_role=liquidity_role,
        )
        return SlippageEstimate(
            side=side,
            liquidity_role=liquidity_role,
            input_price=price,
            adjusted_price=price,
            quantity=quantity,
            slippage_bps=_ZERO,
            slippage_amount_per_unit=_ZERO,
            total_slippage=_ZERO,
        )


@dataclass(frozen=True, slots=True)
class BpsSlippageModel:
    """Apply deterministic basis-point slippage to taker fill prices."""

    taker_slippage_bps: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "taker_slippage_bps",
            _parse_bounded_nonnegative_decimal(
                self.taker_slippage_bps,
                field_name="taker_slippage_bps",
            ),
        )

    @classmethod
    def from_bps(cls, taker_slippage_bps: Decimal) -> BpsSlippageModel:
        """Create a BPS slippage model from an exact Decimal basis-point value."""

        return cls(taker_slippage_bps=taker_slippage_bps)

    @classmethod
    def from_configuration(cls, configuration: SimulationConfiguration) -> BpsSlippageModel:
        """Create a BPS slippage model from canonical simulation configuration."""

        if configuration.slippage_model != BPS_SLIPPAGE_MODEL_NAME:
            raise SimulationConfigurationError(
                "Simulation slippage_model must select the BPS slippage model",
                reason_code="simulation_slippage_model_unsupported",
                context={"slippage_model": configuration.slippage_model},
            )
        if configuration.taker_slippage_bps is None:
            raise SimulationConfigurationError(
                "BPS slippage simulation requires taker_slippage_bps",
                reason_code="simulation_taker_slippage_missing",
                context={"slippage_model": configuration.slippage_model},
            )
        return cls.from_bps(configuration.taker_slippage_bps)

    def estimate(
        self,
        *,
        side: Side,
        price: Decimal,
        quantity: Decimal,
        liquidity_role: LiquidityRole,
    ) -> SlippageEstimate:
        """Return price adjusted by configured taker slippage."""

        side, price, quantity, liquidity_role = _validate_inputs(
            side=side,
            price=price,
            quantity=quantity,
            liquidity_role=liquidity_role,
        )
        if liquidity_role is not LiquidityRole.TAKER or self.taker_slippage_bps == _ZERO:
            return SlippageEstimate(
                side=side,
                liquidity_role=liquidity_role,
                input_price=price,
                adjusted_price=price,
                quantity=quantity,
                slippage_bps=_ZERO,
                slippage_amount_per_unit=_ZERO,
                total_slippage=_ZERO,
            )

        with localcontext(_SLIPPAGE_ARITHMETIC_CONTEXT):
            price_impact = price * self.taker_slippage_bps / _BASIS_POINTS_DENOMINATOR
            adjusted_price = price + price_impact if side is Side.BUY else price - price_impact
            if adjusted_price < _ZERO:
                adjusted_price = _ZERO
            slippage_amount_per_unit = abs(adjusted_price - price)
            total_slippage = slippage_amount_per_unit * quantity

        return SlippageEstimate(
            side=side,
            liquidity_role=liquidity_role,
            input_price=price,
            adjusted_price=adjusted_price,
            quantity=quantity,
            slippage_bps=self.taker_slippage_bps,
            slippage_amount_per_unit=slippage_amount_per_unit,
            total_slippage=total_slippage,
        )


def _validate_inputs(
    *,
    side: Side,
    price: Decimal,
    quantity: Decimal,
    liquidity_role: LiquidityRole,
) -> tuple[Side, Decimal, Decimal, LiquidityRole]:
    if not isinstance(side, Side):
        raise SimulationInputError(
            "Slippage model side must be a canonical Side",
            reason_code="simulation_slippage_side_invalid",
        )
    if not isinstance(liquidity_role, LiquidityRole):
        raise SimulationInputError(
            "Slippage model liquidity_role must be a canonical LiquidityRole",
            reason_code="simulation_slippage_liquidity_role_invalid",
        )
    parsed_price = _parse_bounded_decimal(price, field_name="slippage model price")
    parsed_quantity = _parse_bounded_decimal(quantity, field_name="slippage model quantity")
    if parsed_price < _ZERO:
        msg = "slippage model price must be nonnegative"
        raise ValueError(msg)
    if parsed_quantity <= _ZERO:
        msg = "slippage model quantity must be positive"
        raise ValueError(msg)
    return side, parsed_price, parsed_quantity, liquidity_role


def _parse_bounded_nonnegative_decimal(value: Decimal, *, field_name: str) -> Decimal:
    parsed = _parse_bounded_decimal(value, field_name=field_name)
    if parsed < _ZERO:
        msg = f"{field_name} must be nonnegative"
        raise ValueError(msg)
    return parsed


def _parse_bounded_decimal(value: Decimal, *, field_name: str) -> Decimal:
    parsed = parse_decimal(value, field_name=field_name)
    _validate_decimal_bounds(parsed, field_name=field_name)
    return parsed


def _validate_decimal_bounds(value: Decimal, *, field_name: str) -> None:
    decimal_tuple = value.as_tuple()
    if not isinstance(decimal_tuple.exponent, int):
        msg = f"{field_name} must be finite"
        raise ValueError(msg)
    digits = len(decimal_tuple.digits)
    scale = max(-decimal_tuple.exponent, 0)
    if digits > _MAX_DECIMAL_DIGITS:
        msg = f"{field_name} must have at most {_MAX_DECIMAL_DIGITS} significant digits"
        raise ValueError(msg)
    if scale > _MAX_DECIMAL_SCALE:
        msg = f"{field_name} must have at most {_MAX_DECIMAL_SCALE} fractional digits"
        raise ValueError(msg)
    if value.adjusted() > _MAX_DECIMAL_ADJUSTED_EXPONENT:
        msg = f"{field_name} adjusted exponent must be at most {_MAX_DECIMAL_ADJUSTED_EXPONENT}"
        raise ValueError(msg)
