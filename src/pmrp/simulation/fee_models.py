"""Deterministic fee models for simulated fills."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, runtime_checkable

from pmrp.schemas.enums import LiquidityRole
from pmrp.schemas.numeric import parse_decimal, validate_currency
from pmrp.simulation.errors import SimulationConfigurationError, SimulationInputError

FEE_TABLE_MODEL_NAME = "fee_table_v1"

_BASIS_POINTS_DENOMINATOR = Decimal("10000")
_ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class FeeRule:
    """One explicit exchange fee-table rule for a liquidity role."""

    exchange: str
    liquidity_role: LiquidityRole
    currency: str = "USD"
    fee_rate_bps: Decimal = _ZERO
    fixed_fee: Decimal = _ZERO
    rebate_rate_bps: Decimal = _ZERO
    fixed_rebate: Decimal = _ZERO

    def __post_init__(self) -> None:
        object.__setattr__(self, "exchange", _validate_text(self.exchange, field_name="exchange"))
        if not isinstance(self.liquidity_role, LiquidityRole):
            msg = "liquidity_role must be a canonical LiquidityRole"
            raise TypeError(msg)
        object.__setattr__(self, "currency", validate_currency(self.currency))
        object.__setattr__(
            self,
            "fee_rate_bps",
            _parse_nonnegative_decimal(self.fee_rate_bps, field_name="fee_rate_bps"),
        )
        object.__setattr__(
            self,
            "fixed_fee",
            _parse_nonnegative_decimal(self.fixed_fee, field_name="fixed_fee"),
        )
        object.__setattr__(
            self,
            "rebate_rate_bps",
            _parse_nonnegative_decimal(self.rebate_rate_bps, field_name="rebate_rate_bps"),
        )
        object.__setattr__(
            self,
            "fixed_rebate",
            _parse_nonnegative_decimal(self.fixed_rebate, field_name="fixed_rebate"),
        )

    @classmethod
    def zero(
        cls,
        *,
        exchange: str,
        liquidity_role: LiquidityRole,
        currency: str = "USD",
    ) -> FeeRule:
        """Create an explicit zero-fee rule."""

        return cls(exchange=exchange, liquidity_role=liquidity_role, currency=currency)


@dataclass(frozen=True, slots=True)
class FeeEstimate:
    """Estimated simulated fee and rebate for one fill component."""

    exchange: str
    liquidity_role: LiquidityRole
    currency: str
    notional: Decimal
    fee_amount: Decimal
    rebate_amount: Decimal
    net_fee_amount: Decimal


@runtime_checkable
class FeeModel(Protocol):
    """Pure fee model for simulated fill components."""

    def estimate(
        self,
        *,
        exchange: str,
        price: Decimal,
        quantity: Decimal,
        liquidity_role: LiquidityRole,
    ) -> FeeEstimate:
        """Estimate simulated fees for one fill component."""
        ...


@dataclass(frozen=True, slots=True)
class FeeTableModel:
    """Apply an explicit exchange-specific fee table."""

    rules: tuple[FeeRule, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.rules, tuple):
            msg = "rules must be a tuple of FeeRule values"
            raise TypeError(msg)
        if not self.rules:
            msg = "fee table requires at least one rule"
            raise ValueError(msg)

        seen: set[tuple[str, LiquidityRole]] = set()
        for rule in self.rules:
            if not isinstance(rule, FeeRule):
                msg = "rules must contain only FeeRule values"
                raise TypeError(msg)
            key = (rule.exchange, rule.liquidity_role)
            if key in seen:
                raise SimulationConfigurationError(
                    "Fee table contains duplicate exchange and liquidity role rule",
                    reason_code="simulation_fee_rule_duplicate",
                    context={
                        "exchange": rule.exchange,
                        "liquidity_role": rule.liquidity_role.value,
                    },
                )
            seen.add(key)

    @classmethod
    def from_rules(cls, *rules: FeeRule) -> FeeTableModel:
        """Create a fee-table model from explicit rules."""

        return cls(rules=tuple(rules))

    def estimate(
        self,
        *,
        exchange: str,
        price: Decimal,
        quantity: Decimal,
        liquidity_role: LiquidityRole,
    ) -> FeeEstimate:
        """Estimate fee, rebate, and net fee for one simulated fill component."""

        exchange = _validate_text(exchange, field_name="exchange")
        if not isinstance(liquidity_role, LiquidityRole):
            raise SimulationInputError(
                "Fee model liquidity_role must be a canonical LiquidityRole",
                reason_code="simulation_fee_liquidity_role_invalid",
            )
        parsed_price = parse_decimal(price, field_name="fee model price")
        parsed_quantity = parse_decimal(quantity, field_name="fee model quantity")
        if parsed_price < _ZERO:
            msg = "fee model price must be nonnegative"
            raise ValueError(msg)
        if parsed_quantity <= _ZERO:
            msg = "fee model quantity must be positive"
            raise ValueError(msg)

        rule = self._rule_for(exchange=exchange, liquidity_role=liquidity_role)
        notional = parsed_price * parsed_quantity
        fee_amount = (notional * rule.fee_rate_bps / _BASIS_POINTS_DENOMINATOR) + rule.fixed_fee
        rebate_amount = (
            notional * rule.rebate_rate_bps / _BASIS_POINTS_DENOMINATOR
        ) + rule.fixed_rebate
        return FeeEstimate(
            exchange=exchange,
            liquidity_role=liquidity_role,
            currency=rule.currency,
            notional=notional,
            fee_amount=fee_amount,
            rebate_amount=rebate_amount,
            net_fee_amount=fee_amount - rebate_amount,
        )

    def _rule_for(self, *, exchange: str, liquidity_role: LiquidityRole) -> FeeRule:
        for rule in self.rules:
            if rule.exchange == exchange and rule.liquidity_role is liquidity_role:
                return rule
        raise SimulationConfigurationError(
            "Fee table is missing a rule for exchange and liquidity role",
            reason_code="simulation_fee_rule_missing",
            context={"exchange": exchange, "liquidity_role": liquidity_role.value},
        )


def _parse_nonnegative_decimal(value: Decimal, *, field_name: str) -> Decimal:
    parsed = parse_decimal(value, field_name=field_name)
    if parsed < _ZERO:
        msg = f"{field_name} must be nonnegative"
        raise ValueError(msg)
    return parsed


def _validate_text(value: str, *, field_name: str) -> str:
    if type(value) is not str:
        msg = f"{field_name} must be a string"
        raise TypeError(msg)
    if value == "" or value.strip() != value:
        msg = f"{field_name} must be nonempty without surrounding whitespace"
        raise ValueError(msg)
    return value
