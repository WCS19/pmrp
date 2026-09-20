"""Deterministic rejection models for simulated orders."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol, runtime_checkable

from pmrp.schemas.enums import MarketStatus
from pmrp.schemas.numeric import parse_decimal
from pmrp.simulation.errors import SimulationInputError

BOUNDED_REJECTION_MODEL_NAME = "bounded_rejection_v1"

_ZERO = Decimal("0")


class RejectionReason(StrEnum):
    """Stable simulation rejection reason codes."""

    ACCEPTED = "simulation_order_accepted"
    INSUFFICIENT_BALANCE = "simulation_insufficient_balance"
    INVALID_PRICE = "simulation_invalid_price"
    INVALID_QUANTITY = "simulation_invalid_quantity"
    MARKET_CLOSED = "simulation_market_closed"


@dataclass(frozen=True, slots=True)
class RejectionDecision:
    """Deterministic simulated order rejection decision."""

    accepted: bool
    reason_code: RejectionReason
    reason_text: str

    @property
    def rejected(self) -> bool:
        """Return whether the simulated order is rejected."""

        return not self.accepted


@runtime_checkable
class RejectionModel(Protocol):
    """Pure pre-submit rejection model for simulated orders."""

    def evaluate(
        self,
        *,
        market_status: MarketStatus,
        price: Decimal | None,
        quantity: Decimal,
        required_balance: Decimal | None = None,
        available_balance: Decimal | None = None,
    ) -> RejectionDecision:
        """Return a simulated accept/reject decision."""
        ...


@dataclass(frozen=True, slots=True)
class BoundedRejectionModel:
    """Reject invalid prices, quantities, closed markets, and insufficient balance."""

    min_price: Decimal = _ZERO
    max_price: Decimal | None = Decimal("1")
    min_quantity: Decimal = Decimal("0.00000001")
    max_quantity: Decimal | None = None
    open_statuses: tuple[MarketStatus, ...] = (MarketStatus.OPEN,)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "min_price",
            _parse_nonnegative_decimal(self.min_price, field_name="min_price"),
        )
        if self.max_price is not None:
            object.__setattr__(
                self,
                "max_price",
                _parse_nonnegative_decimal(self.max_price, field_name="max_price"),
            )
        object.__setattr__(
            self,
            "min_quantity",
            _parse_positive_decimal(self.min_quantity, field_name="min_quantity"),
        )
        if self.max_quantity is not None:
            object.__setattr__(
                self,
                "max_quantity",
                _parse_positive_decimal(self.max_quantity, field_name="max_quantity"),
            )
        if self.max_price is not None and self.max_price < self.min_price:
            msg = "max_price must be greater than or equal to min_price"
            raise ValueError(msg)
        if self.max_quantity is not None and self.max_quantity < self.min_quantity:
            msg = "max_quantity must be greater than or equal to min_quantity"
            raise ValueError(msg)
        _validate_open_statuses(self.open_statuses)

    def evaluate(
        self,
        *,
        market_status: MarketStatus,
        price: Decimal | None,
        quantity: Decimal,
        required_balance: Decimal | None = None,
        available_balance: Decimal | None = None,
    ) -> RejectionDecision:
        """Return the first deterministic rejection reason, or acceptance."""

        if not isinstance(market_status, MarketStatus):
            raise SimulationInputError(
                "Rejection model market_status must be a canonical MarketStatus",
                reason_code="simulation_rejection_market_status_invalid",
            )
        parsed_price = _parse_optional_decimal(price, field_name="order price")
        parsed_quantity = parse_decimal(quantity, field_name="order quantity")
        parsed_required_balance = _parse_optional_nonnegative_decimal(
            required_balance,
            field_name="required_balance",
        )
        parsed_available_balance = _parse_optional_nonnegative_decimal(
            available_balance,
            field_name="available_balance",
        )

        if parsed_price is None:
            return _reject(RejectionReason.INVALID_PRICE, "price is required")
        if parsed_price < _ZERO:
            return _reject(RejectionReason.INVALID_PRICE, "price must be nonnegative")
        if parsed_price < self.min_price:
            return _reject(RejectionReason.INVALID_PRICE, "price is below the minimum")
        if self.max_price is not None and parsed_price > self.max_price:
            return _reject(RejectionReason.INVALID_PRICE, "price is above the maximum")
        if parsed_quantity <= _ZERO:
            return _reject(RejectionReason.INVALID_QUANTITY, "quantity must be positive")
        if parsed_quantity < self.min_quantity:
            return _reject(RejectionReason.INVALID_QUANTITY, "quantity is below the minimum")
        if self.max_quantity is not None and parsed_quantity > self.max_quantity:
            return _reject(RejectionReason.INVALID_QUANTITY, "quantity is above the maximum")
        if market_status not in self.open_statuses:
            return _reject(RejectionReason.MARKET_CLOSED, "market is not open for trading")
        if parsed_required_balance is not None and parsed_available_balance is None:
            return _reject(
                RejectionReason.INSUFFICIENT_BALANCE,
                "available balance is unavailable",
            )
        if (
            parsed_available_balance is not None
            and parsed_required_balance is not None
            and parsed_available_balance < parsed_required_balance
        ):
            return _reject(
                RejectionReason.INSUFFICIENT_BALANCE,
                "available balance is below required balance",
            )
        return _accept()


def _reject(reason_code: RejectionReason, reason_text: str) -> RejectionDecision:
    return RejectionDecision(accepted=False, reason_code=reason_code, reason_text=reason_text)


def _accept() -> RejectionDecision:
    return RejectionDecision(
        accepted=True,
        reason_code=RejectionReason.ACCEPTED,
        reason_text="order accepted by simulation rejection model",
    )


def _parse_optional_nonnegative_decimal(
    value: Decimal | None,
    *,
    field_name: str,
) -> Decimal | None:
    if value is None:
        return None
    return _parse_nonnegative_decimal(value, field_name=field_name)


def _parse_optional_decimal(value: Decimal | None, *, field_name: str) -> Decimal | None:
    if value is None:
        return None
    return parse_decimal(value, field_name=field_name)


def _parse_nonnegative_decimal(value: Decimal, *, field_name: str) -> Decimal:
    parsed = parse_decimal(value, field_name=field_name)
    if parsed < _ZERO:
        msg = f"{field_name} must be nonnegative"
        raise ValueError(msg)
    return parsed


def _parse_positive_decimal(value: Decimal, *, field_name: str) -> Decimal:
    parsed = parse_decimal(value, field_name=field_name)
    if parsed <= _ZERO:
        msg = f"{field_name} must be positive"
        raise ValueError(msg)
    return parsed


def _validate_open_statuses(open_statuses: tuple[MarketStatus, ...]) -> None:
    if not isinstance(open_statuses, tuple):
        msg = "open_statuses must be a tuple of MarketStatus values"
        raise TypeError(msg)
    if not open_statuses:
        msg = "open_statuses must not be empty"
        raise ValueError(msg)
    if any(not isinstance(status, MarketStatus) for status in open_statuses):
        msg = "open_statuses must contain only MarketStatus values"
        raise TypeError(msg)
