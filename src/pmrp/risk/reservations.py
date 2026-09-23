"""Capital reservation value objects for pre-trade risk concurrency."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from pmrp.risk.errors import RiskConfigurationError, RiskInputError
from pmrp.schemas.enums import ExchangeName, RiskDecisionStatus
from pmrp.schemas.identifiers import AccountId, IntentId, MarketId, StrategyId
from pmrp.schemas.numeric import parse_decimal, validate_currency
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.risk import RiskDecision
from pmrp.schemas.serialization import canonical_sha256
from pmrp.schemas.time import parse_utc_datetime

_RESERVATION_ID_MAX_LENGTH = 128
_RESERVATION_HASH_PREFIX_LENGTH = 32


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


class CapitalReservationIdGenerator(Protocol):
    """Generate durable reservation identifiers from approved risk content."""

    def reservation_id(
        self,
        *,
        intent: OrderIntent,
        decision: RiskDecision,
        exchange: ExchangeName,
        account_id: AccountId,
        currency: str,
    ) -> str:
        """Return a stable capital reservation identifier."""
        ...


@dataclass(frozen=True, slots=True)
class HashingCapitalReservationIdGenerator:
    """Generate deterministic capital reservation IDs from canonical approval inputs."""

    def reservation_id(
        self,
        *,
        intent: OrderIntent,
        decision: RiskDecision,
        exchange: ExchangeName,
        account_id: AccountId,
        currency: str,
    ) -> str:
        """Return the same reservation ID for identical approved inputs."""

        digest = canonical_sha256(
            {
                "account_id": str(account_id),
                "approval_expires_at": decision.approval_expires_at,
                "approved_limit_price": decision.approved_limit_price,
                "approved_quantity": decision.approved_quantity,
                "correlation_id": decision.correlation_id,
                "currency": currency,
                "evaluated_at": decision.evaluated_at,
                "exchange": exchange,
                "intent_id": intent.intent_id,
                "risk_decision_id": decision.risk_decision_id,
            }
        ).removeprefix("sha256:")
        return f"reserve_{digest[:_RESERVATION_HASH_PREFIX_LENGTH]}"


@dataclass(frozen=True, slots=True)
class CapitalReservationFactory:
    """Build active capital reservations from approved risk decisions."""

    id_generator: CapitalReservationIdGenerator = field(
        default_factory=HashingCapitalReservationIdGenerator
    )

    def __post_init__(self) -> None:
        if not callable(getattr(self.id_generator, "reservation_id", None)):
            raise RiskConfigurationError(
                "capital reservation ID generator must implement reservation_id"
            )

    def build(
        self,
        intent: OrderIntent,
        decision: RiskDecision,
        *,
        exchange: ExchangeName,
        account_id: AccountId,
        currency: str,
    ) -> CapitalReservation:
        """Return the active reservation authorized by one approved risk decision."""

        _validate_reservation_pair(intent, decision)
        exchange = ExchangeName(exchange)
        account_id = AccountId(str(account_id))
        currency = validate_currency(currency)
        approved_quantity, approved_limit_price = _approved_reservation_values(decision)
        expires_at = decision.approval_expires_at
        if expires_at is None:
            raise RiskInputError("capital reservation requires approval_expires_at")
        reservation_id = self.id_generator.reservation_id(
            intent=intent,
            decision=decision,
            exchange=exchange,
            account_id=account_id,
            currency=currency,
        )
        _validate_reservation_id(reservation_id)

        return CapitalReservation(
            reservation_id=reservation_id,
            intent_id=intent.intent_id,
            strategy_id=intent.strategy_id,
            exchange=exchange,
            account_id=account_id,
            market_id=intent.market_id,
            quantity=approved_quantity,
            notional=approved_quantity * approved_limit_price,
            currency=currency,
            status=CapitalReservationStatus.ACTIVE,
            created_at=decision.evaluated_at,
            expires_at=expires_at,
            released_at=None,
        )


def build_capital_reservation(
    intent: OrderIntent,
    decision: RiskDecision,
    *,
    exchange: ExchangeName,
    account_id: AccountId,
    currency: str,
    id_generator: CapitalReservationIdGenerator | None = None,
) -> CapitalReservation:
    """Return an active capital reservation using the default deterministic factory."""

    factory = CapitalReservationFactory(
        id_generator=(
            id_generator if id_generator is not None else HashingCapitalReservationIdGenerator()
        )
    )
    return factory.build(
        intent,
        decision,
        exchange=exchange,
        account_id=account_id,
        currency=currency,
    )


def _validate_reservation_pair(intent: OrderIntent, decision: RiskDecision) -> None:
    if not isinstance(intent, OrderIntent):
        raise RiskInputError("capital reservation construction requires an OrderIntent")
    if not isinstance(decision, RiskDecision):
        raise RiskInputError("capital reservation construction requires a RiskDecision")
    if decision.status is not RiskDecisionStatus.APPROVED:
        raise RiskInputError("capital reservation construction requires an approved risk decision")
    if decision.intent_id != intent.intent_id:
        raise RiskInputError("risk decision intent_id must match order intent")
    if decision.correlation_id != intent.correlation_id:
        raise RiskInputError("risk decision correlation_id must match order intent")
    if decision.approved_quantity is None or decision.approved_limit_price is None:
        raise RiskInputError("approved risk decision requires quantity and limit price")
    if decision.approved_quantity > intent.quantity:
        raise RiskInputError("approved quantity cannot exceed requested intent quantity")


def _approved_reservation_values(decision: RiskDecision) -> tuple[Decimal, Decimal]:
    if decision.approved_quantity is None or decision.approved_limit_price is None:
        raise RiskInputError("approved risk decision requires quantity and limit price")
    return decision.approved_quantity, decision.approved_limit_price
