"""Derive approved order contracts from approved risk decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol

from pmrp.risk.errors import RiskConfigurationError, RiskInputError
from pmrp.schemas.enums import RiskDecisionStatus
from pmrp.schemas.identifiers import AccountId, OrderId
from pmrp.schemas.orders import ApprovedOrder, OrderIntent
from pmrp.schemas.risk import RiskDecision
from pmrp.schemas.serialization import canonical_sha256

_APPROVED_ORDER_HASH_PREFIX_LENGTH = 32
_CLIENT_ORDER_HASH_PREFIX_LENGTH = 48
_IDEMPOTENCY_HASH_PREFIX_LENGTH = 48
_REFERENCE_PREFIX_MAX_LENGTH = 64
_EXCHANGE_MAX_LENGTH = 64


@dataclass(frozen=True, slots=True)
class ApprovedOrderReferences:
    """Generated identifiers for one risk-approved order."""

    order_id: OrderId
    client_order_id: str
    idempotency_key: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "order_id", OrderId(str(self.order_id)))
        _validate_generated_reference(self.client_order_id, field_name="client_order_id")
        _validate_generated_reference(self.idempotency_key, field_name="idempotency_key")


class ApprovedOrderReferenceGenerator(Protocol):
    """Generate deterministic order references for approved order contracts."""

    def references(
        self,
        *,
        intent: OrderIntent,
        decision: RiskDecision,
        exchange: str,
        account_id: AccountId,
    ) -> ApprovedOrderReferences:
        """Return stable order references for the approved intent and decision."""
        ...


@dataclass(frozen=True, slots=True)
class HashingApprovedOrderReferenceGenerator:
    """Generate approved-order references from canonical approval content."""

    client_order_prefix: str = "pmrp"
    idempotency_prefix: str = "approved-order"

    def __post_init__(self) -> None:
        _validate_reference_prefix(self.client_order_prefix, field_name="client_order_prefix")
        _validate_reference_prefix(self.idempotency_prefix, field_name="idempotency_prefix")

    def references(
        self,
        *,
        intent: OrderIntent,
        decision: RiskDecision,
        exchange: str,
        account_id: AccountId,
    ) -> ApprovedOrderReferences:
        """Return stable references for identical approval inputs."""

        digest = canonical_sha256(
            {
                "account_id": str(account_id),
                "approval_expires_at": decision.approval_expires_at,
                "approved_limit_price": decision.approved_limit_price,
                "approved_quantity": decision.approved_quantity,
                "correlation_id": decision.correlation_id,
                "evaluated_at": decision.evaluated_at,
                "exchange": exchange,
                "intent_id": intent.intent_id,
                "risk_decision_id": decision.risk_decision_id,
            }
        ).removeprefix("sha256:")
        return ApprovedOrderReferences(
            order_id=OrderId(f"{OrderId.prefix}{digest[:_APPROVED_ORDER_HASH_PREFIX_LENGTH]}"),
            client_order_id=(
                f"{self.client_order_prefix}-{digest[:_CLIENT_ORDER_HASH_PREFIX_LENGTH]}"
            ),
            idempotency_key=(
                f"{self.idempotency_prefix}-{digest[:_IDEMPOTENCY_HASH_PREFIX_LENGTH]}"
            ),
        )


@dataclass(frozen=True, slots=True)
class ApprovedOrderFactory:
    """Create approved-order contracts from validated risk decisions."""

    reference_generator: ApprovedOrderReferenceGenerator = field(
        default_factory=HashingApprovedOrderReferenceGenerator
    )

    def __post_init__(self) -> None:
        if not callable(getattr(self.reference_generator, "references", None)):
            raise RiskConfigurationError(
                "approved order reference generator must implement references"
            )

    def build(
        self,
        intent: OrderIntent,
        decision: RiskDecision,
        *,
        exchange: str,
        account_id: AccountId,
    ) -> ApprovedOrder:
        """Return the approved-order contract authorized by one risk decision."""

        _validate_approval_pair(intent, decision)
        exchange = _validate_exchange(exchange)
        account_id = AccountId(str(account_id))
        approved_quantity, approved_limit_price = _approved_order_values(decision)
        references = self.reference_generator.references(
            intent=intent,
            decision=decision,
            exchange=exchange,
            account_id=account_id,
        )
        if not isinstance(references, ApprovedOrderReferences):
            raise RiskConfigurationError(
                "approved order reference generator must return ApprovedOrderReferences"
            )

        return ApprovedOrder(
            order_id=references.order_id,
            intent_id=intent.intent_id,
            strategy_id=intent.strategy_id,
            risk_decision_id=decision.risk_decision_id,
            exchange=exchange,
            account_id=account_id,
            market_id=intent.market_id,
            contract_id=intent.contract_id,
            outcome_id=intent.outcome_id,
            side=intent.side,
            quantity=approved_quantity,
            limit_price=approved_limit_price,
            order_type=intent.order_type,
            time_in_force=intent.time_in_force,
            post_only=intent.post_only,
            reduce_only=intent.reduce_only,
            approved_at=decision.evaluated_at,
            approval_expires_at=decision.approval_expires_at,
            client_order_id=references.client_order_id,
            idempotency_key=references.idempotency_key,
            correlation_id=intent.correlation_id,
        )


def build_approved_order(
    intent: OrderIntent,
    decision: RiskDecision,
    *,
    exchange: str,
    account_id: AccountId,
    reference_generator: ApprovedOrderReferenceGenerator | None = None,
) -> ApprovedOrder:
    """Return an approved-order contract using the default deterministic factory."""

    factory = ApprovedOrderFactory(
        reference_generator=(
            reference_generator
            if reference_generator is not None
            else HashingApprovedOrderReferenceGenerator()
        )
    )
    return factory.build(
        intent,
        decision,
        exchange=exchange,
        account_id=account_id,
    )


def _validate_approval_pair(intent: OrderIntent, decision: RiskDecision) -> None:
    if not isinstance(intent, OrderIntent):
        raise RiskInputError("approved order construction requires an OrderIntent")
    if not isinstance(decision, RiskDecision):
        raise RiskInputError("approved order construction requires a RiskDecision")
    if decision.status is not RiskDecisionStatus.APPROVED:
        raise RiskInputError("approved order construction requires an approved risk decision")
    if decision.intent_id != intent.intent_id:
        raise RiskInputError("risk decision intent_id must match order intent")
    if decision.correlation_id != intent.correlation_id:
        raise RiskInputError("risk decision correlation_id must match order intent")
    if decision.approved_quantity is None or decision.approved_limit_price is None:
        raise RiskInputError("approved risk decision requires quantity and limit price")
    if decision.approved_quantity > intent.quantity:
        raise RiskInputError("approved quantity cannot exceed requested intent quantity")


def _approved_order_values(decision: RiskDecision) -> tuple[Decimal, Decimal]:
    if decision.approved_quantity is None or decision.approved_limit_price is None:
        raise RiskInputError("approved risk decision requires quantity and limit price")
    return decision.approved_quantity, decision.approved_limit_price


def _validate_exchange(exchange: str) -> str:
    if type(exchange) is not str:
        msg = "approved order exchange must be a string"
        raise TypeError(msg)
    if exchange == "":
        raise RiskInputError("approved order exchange must not be empty")
    if len(exchange) > _EXCHANGE_MAX_LENGTH:
        raise RiskInputError("approved order exchange must be at most 64 characters")
    return exchange


def _validate_reference_prefix(prefix: str, *, field_name: str) -> None:
    if type(prefix) is not str:
        msg = f"{field_name} must be a string"
        raise TypeError(msg)
    if prefix == "":
        raise RiskConfigurationError(f"{field_name} must not be empty")
    if len(prefix) > _REFERENCE_PREFIX_MAX_LENGTH:
        raise RiskConfigurationError(f"{field_name} must be at most 64 characters")


def _validate_generated_reference(reference: str, *, field_name: str) -> None:
    if type(reference) is not str:
        msg = f"{field_name} must be a string"
        raise TypeError(msg)
    if reference == "":
        raise RiskConfigurationError(f"{field_name} must not be empty")
    if len(reference) > 256:
        raise RiskConfigurationError(f"{field_name} must be at most 256 characters")
