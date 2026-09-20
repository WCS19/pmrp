"""Deterministic simulated exchange admission primitives."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable

from pmrp.schemas.enums import MarketStatus
from pmrp.schemas.numeric import parse_decimal
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.serialization import canonical_sha256, to_canonical_data
from pmrp.schemas.time import parse_utc_datetime
from pmrp.simulation.errors import SimulationConfigurationError, SimulationInputError
from pmrp.simulation.latency_models import LatencyModel
from pmrp.simulation.rejection_models import RejectionDecision, RejectionModel
from pmrp.simulation.results import SimulationSourceType

SIMULATED_EXCHANGE_ADMISSION_MODEL_NAME = "simulated_exchange_admission_v1"


@dataclass(frozen=True, slots=True)
class SimulatedExchangeOrderAdmission:
    """Deterministic admission result for one simulated order intent."""

    intent: OrderIntent
    market_status: MarketStatus
    rejection_decision: RejectionDecision
    submitted_at: datetime
    accepted_at: datetime | None
    activates_at: datetime | None
    required_balance: Decimal | None = None
    available_balance: Decimal | None = None
    source_type: SimulationSourceType = SimulationSourceType.SIMULATED_OUTPUT

    def __post_init__(self) -> None:
        if not isinstance(self.intent, OrderIntent):
            raise SimulationInputError(
                "Simulated exchange admission requires an OrderIntent",
                reason_code="simulation_exchange_intent_invalid",
            )
        if not isinstance(self.market_status, MarketStatus):
            raise SimulationInputError(
                "Simulated exchange market_status must be a canonical MarketStatus",
                reason_code="simulation_exchange_market_status_invalid",
            )
        if not isinstance(self.rejection_decision, RejectionDecision):
            msg = "rejection_decision must be a RejectionDecision"
            raise TypeError(msg)
        object.__setattr__(self, "submitted_at", parse_utc_datetime(self.submitted_at))
        _validate_activation_lineage(
            rejection_decision=self.rejection_decision,
            accepted_at=self.accepted_at,
            activates_at=self.activates_at,
        )
        if self.accepted_at is not None:
            object.__setattr__(self, "accepted_at", parse_utc_datetime(self.accepted_at))
        if self.activates_at is not None:
            object.__setattr__(self, "activates_at", parse_utc_datetime(self.activates_at))
        if (
            self.accepted_at is not None
            and self.activates_at is not None
            and self.activates_at < self.accepted_at
        ):
            raise SimulationConfigurationError(
                "Simulated admission activates_at must be at or after accepted_at",
                reason_code="simulation_exchange_activation_order_invalid",
            )
        object.__setattr__(
            self,
            "required_balance",
            _parse_optional_decimal(self.required_balance, field_name="required_balance"),
        )
        object.__setattr__(
            self,
            "available_balance",
            _parse_optional_decimal(self.available_balance, field_name="available_balance"),
        )
        if self.source_type is not SimulationSourceType.SIMULATED_OUTPUT:
            raise SimulationConfigurationError(
                "Simulated exchange admissions must be classified as simulated output",
                reason_code="simulation_exchange_source_type_invalid",
                context={"source_type": str(self.source_type)},
            )

    @property
    def accepted(self) -> bool:
        """Return whether the simulated exchange accepted the order intent."""

        return self.rejection_decision.accepted

    @property
    def rejected(self) -> bool:
        """Return whether the simulated exchange rejected the order intent."""

        return self.rejection_decision.rejected

    @property
    def admission_hash(self) -> str:
        """Return the deterministic hash for this admission result."""

        return canonical_sha256(self.canonical_payload())

    def canonical_payload(self) -> Mapping[str, object]:
        """Return stable JSON-compatible admission data."""

        return {
            "accepted_at": self.accepted_at,
            "activates_at": self.activates_at,
            "admission_model": SIMULATED_EXCHANGE_ADMISSION_MODEL_NAME,
            "available_balance": self.available_balance,
            "intent": to_canonical_data(self.intent),
            "market_status": self.market_status,
            "rejection_decision": {
                "accepted": self.rejection_decision.accepted,
                "reason_code": self.rejection_decision.reason_code,
                "reason_text": self.rejection_decision.reason_text,
            },
            "required_balance": self.required_balance,
            "source_type": self.source_type,
            "submitted_at": self.submitted_at,
        }


@runtime_checkable
class SimulatedExchange(Protocol):
    """Pure simulated exchange admission interface."""

    def admit_order(
        self,
        *,
        intent: OrderIntent,
        market_status: MarketStatus,
        submitted_at: datetime,
        required_balance: Decimal | None = None,
        available_balance: Decimal | None = None,
    ) -> SimulatedExchangeOrderAdmission:
        """Evaluate one simulated order intent without external submission."""
        ...


@dataclass(frozen=True, slots=True)
class DeterministicSimulatedExchange:
    """Simulated exchange admission layer composed from deterministic models."""

    rejection_model: RejectionModel
    latency_model: LatencyModel

    def __post_init__(self) -> None:
        if not isinstance(self.rejection_model, RejectionModel):
            msg = "rejection_model must implement RejectionModel"
            raise TypeError(msg)
        if not isinstance(self.latency_model, LatencyModel):
            msg = "latency_model must implement LatencyModel"
            raise TypeError(msg)

    def admit_order(
        self,
        *,
        intent: OrderIntent,
        market_status: MarketStatus,
        submitted_at: datetime,
        required_balance: Decimal | None = None,
        available_balance: Decimal | None = None,
    ) -> SimulatedExchangeOrderAdmission:
        """Evaluate rejection and activation timing for a simulated order intent."""

        intent = _validate_intent(intent)
        market_status = _validate_market_status(market_status)
        submitted_at = parse_utc_datetime(submitted_at)
        required_balance = _parse_optional_decimal(
            required_balance,
            field_name="required_balance",
        )
        available_balance = _parse_optional_decimal(
            available_balance,
            field_name="available_balance",
        )

        rejection_decision = self.rejection_model.evaluate(
            market_status=market_status,
            price=intent.limit_price,
            quantity=intent.quantity,
            required_balance=required_balance,
            available_balance=available_balance,
        )
        accepted_at = submitted_at if rejection_decision.accepted else None
        activates_at = (
            self.latency_model.activation_time(accepted_at=accepted_at)
            if accepted_at is not None
            else None
        )
        return SimulatedExchangeOrderAdmission(
            intent=intent,
            market_status=market_status,
            rejection_decision=rejection_decision,
            submitted_at=submitted_at,
            accepted_at=accepted_at,
            activates_at=activates_at,
            required_balance=required_balance,
            available_balance=available_balance,
        )


def _validate_intent(intent: OrderIntent) -> OrderIntent:
    if not isinstance(intent, OrderIntent):
        raise SimulationInputError(
            "Simulated exchange requires an OrderIntent",
            reason_code="simulation_exchange_intent_invalid",
        )
    return intent


def _validate_market_status(market_status: MarketStatus) -> MarketStatus:
    if not isinstance(market_status, MarketStatus):
        raise SimulationInputError(
            "Simulated exchange market_status must be a canonical MarketStatus",
            reason_code="simulation_exchange_market_status_invalid",
        )
    return market_status


def _parse_optional_decimal(value: Decimal | None, *, field_name: str) -> Decimal | None:
    if value is None:
        return None
    return parse_decimal(value, field_name=field_name)


def _validate_activation_lineage(
    *,
    rejection_decision: RejectionDecision,
    accepted_at: datetime | None,
    activates_at: datetime | None,
) -> None:
    if rejection_decision.accepted:
        if accepted_at is None or activates_at is None:
            raise SimulationConfigurationError(
                "Accepted simulated admissions require accepted_at and activates_at",
                reason_code="simulation_exchange_activation_missing",
            )
        return
    if accepted_at is not None or activates_at is not None:
        raise SimulationConfigurationError(
            "Rejected simulated admissions must not include activation timestamps",
            reason_code="simulation_exchange_rejected_activation_invalid",
        )
