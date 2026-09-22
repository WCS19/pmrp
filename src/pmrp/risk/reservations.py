"""Capital reservation value objects for pre-trade risk concurrency."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pmrp.risk.errors import RiskConfigurationError
from pmrp.schemas.enums import ExchangeName
from pmrp.schemas.identifiers import AccountId, IntentId, MarketId, StrategyId
from pmrp.schemas.numeric import parse_decimal, validate_currency
from pmrp.schemas.time import parse_utc_datetime

_RESERVATION_ID_MAX_LENGTH = 128


class CapitalReservationStatus(StrEnum):
    """Lifecycle states for durable pre-trade capital reservations."""

    ACTIVE = "active"
    RELEASED = "released"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class CapitalReservation:
    """Immutable reservation preventing concurrent approvals from overspending limits."""

    reservation_id: str
    intent_id: IntentId
    strategy_id: StrategyId
    exchange: ExchangeName
    account_id: AccountId
    market_id: MarketId
    quantity: Decimal
    notional: Decimal
    currency: str
    status: CapitalReservationStatus
    created_at: datetime
    expires_at: datetime
    released_at: datetime | None = None

    def __post_init__(self) -> None:
        _validate_reservation_id(self.reservation_id)
        quantity = parse_decimal(self.quantity, field_name="capital reservation quantity")
        notional = parse_decimal(self.notional, field_name="capital reservation notional")
        if quantity <= Decimal("0"):
            raise RiskConfigurationError("capital reservation quantity must be positive")
        if notional <= Decimal("0"):
            raise RiskConfigurationError("capital reservation notional must be positive")

        created_at = parse_utc_datetime(self.created_at)
        expires_at = parse_utc_datetime(self.expires_at)
        released_at = None if self.released_at is None else parse_utc_datetime(self.released_at)
        status = (
            self.status
            if isinstance(self.status, CapitalReservationStatus)
            else CapitalReservationStatus(self.status)
        )

        if expires_at <= created_at:
            raise RiskConfigurationError("capital reservation expires_at must be after created_at")
        if status is CapitalReservationStatus.ACTIVE and released_at is not None:
            raise RiskConfigurationError("active capital reservation cannot have released_at")
        if status is not CapitalReservationStatus.ACTIVE and released_at is None:
            raise RiskConfigurationError("released capital reservation requires released_at")
        if released_at is not None and released_at < created_at:
            raise RiskConfigurationError(
                "capital reservation released_at cannot precede created_at"
            )

        object.__setattr__(self, "intent_id", IntentId(str(self.intent_id)))
        object.__setattr__(self, "strategy_id", StrategyId(str(self.strategy_id)))
        object.__setattr__(self, "exchange", ExchangeName(self.exchange))
        object.__setattr__(self, "account_id", AccountId(str(self.account_id)))
        object.__setattr__(self, "market_id", MarketId(str(self.market_id)))
        object.__setattr__(self, "quantity", quantity)
        object.__setattr__(self, "notional", notional)
        object.__setattr__(self, "currency", validate_currency(self.currency))
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "expires_at", expires_at)
        object.__setattr__(self, "released_at", released_at)


def _validate_reservation_id(reservation_id: str) -> None:
    if type(reservation_id) is not str:
        msg = "capital reservation ID must be a string"
        raise TypeError(msg)
    if reservation_id == "":
        raise RiskConfigurationError("capital reservation ID must not be empty")
    if len(reservation_id) > _RESERVATION_ID_MAX_LENGTH:
        raise RiskConfigurationError("capital reservation ID must be at most 128 characters")
