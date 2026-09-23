"""Canonical event envelope schema."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Self

from pydantic import Field, field_serializer, field_validator, model_validator

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.enums import DataQualityFlag, HealthStatus, RiskDecisionStatus
from pmrp.schemas.identifiers import (
    AccountId,
    CausationRef,
    CorrelationId,
    EventId,
    MarketId,
    OrderId,
    ReplaySessionId,
    SimulationSessionId,
    StrategyId,
)
from pmrp.schemas.immutability import freeze_canonical_mapping, thaw_canonical_mapping
from pmrp.schemas.market_data import OrderBookDelta, OrderBookSnapshot, Trade
from pmrp.schemas.orders import ApprovedOrder, OrderIntent
from pmrp.schemas.risk import KillSwitchState, RiskBreach, RiskDecision, RiskInputSnapshot
from pmrp.schemas.strategy import Signal, StrategyInstance
from pmrp.schemas.time import UTCDateTime
from pmrp.schemas.versions import SchemaVersion

_DOTTED_EVENT_TYPE_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$"
MARKET_ORDER_BOOK_DELTA_EVENT_TYPE = "market.order_book_delta"
MARKET_ORDER_BOOK_SNAPSHOT_EVENT_TYPE = "market.order_book_snapshot"
MARKET_TRADE_OBSERVED_EVENT_TYPE = "market.trade_observed"
RISK_CHECK_REQUESTED_EVENT_TYPE = "risk.check_requested"
RISK_APPROVED_EVENT_TYPE = "risk.approved"
RISK_REJECTED_EVENT_TYPE = "risk.rejected"
RISK_LIMIT_BREACHED_EVENT_TYPE = "risk.limit_breached"
RISK_KILL_SWITCH_ACTIVATED_EVENT_TYPE = "risk.kill_switch_activated"
RISK_KILL_SWITCH_RELEASED_EVENT_TYPE = "risk.kill_switch_released"
STRATEGY_STARTED_EVENT_TYPE = "strategy.started"
STRATEGY_STOPPED_EVENT_TYPE = "strategy.stopped"
STRATEGY_HEALTH_CHANGED_EVENT_TYPE = "strategy.health_changed"
STRATEGY_SIGNAL_GENERATED_EVENT_TYPE = "strategy.signal_generated"


class EventEnvelope(CanonicalModel):
    event_id: EventId
    event_type: str = Field(
        min_length=1,
        max_length=128,
        pattern=_DOTTED_EVENT_TYPE_PATTERN,
    )
    schema_version: SchemaVersion

    occurred_at: UTCDateTime
    received_at: UTCDateTime
    published_at: UTCDateTime

    producer: str = Field(min_length=1, max_length=128)
    exchange: str | None = Field(default=None, min_length=1, max_length=64)
    market_id: MarketId | None = None
    account_id: AccountId | None = None
    strategy_id: StrategyId | None = None
    order_id: OrderId | None = None

    correlation_id: CorrelationId
    causation_id: CausationRef | None = None
    trace_id: str | None = Field(default=None, min_length=1, max_length=128)

    replay_session_id: ReplaySessionId | None = None
    simulation_session_id: SimulationSessionId | None = None

    quality_flags: tuple[DataQualityFlag, ...] = ()
    attributes: Mapping[str, object] = Field(default_factory=dict)

    @field_validator("attributes")
    @classmethod
    def validate_attributes(cls, value: Mapping[str, object]) -> Mapping[str, object]:
        return freeze_canonical_mapping(value, field_name="event attributes")

    @field_serializer("attributes")
    def serialize_attributes(self, value: Mapping[str, object]) -> dict[str, object]:
        return thaw_canonical_mapping(value)


class StrategyStartedEvent(CanonicalModel):
    envelope: EventEnvelope
    strategy: StrategyInstance

    @model_validator(mode="after")
    def validate_envelope(self) -> Self:
        _validate_event_type(self.envelope, STRATEGY_STARTED_EVENT_TYPE)
        _validate_strategy_lineage(
            self.envelope.strategy_id,
            self.strategy.strategy_id,
            field_name="strategy.strategy_id",
        )
        return self


class StrategyStoppedEvent(CanonicalModel):
    envelope: EventEnvelope
    strategy_id: StrategyId
    reason: str = Field(min_length=1, max_length=1024)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        return _validate_required_text(value, field_name="strategy stop reason")

    @model_validator(mode="after")
    def validate_envelope(self) -> Self:
        _validate_event_type(self.envelope, STRATEGY_STOPPED_EVENT_TYPE)
        _validate_strategy_lineage(
            self.envelope.strategy_id,
            self.strategy_id,
            field_name="strategy_id",
        )
        return self


class StrategyHealthChangedEvent(CanonicalModel):
    envelope: EventEnvelope
    strategy_id: StrategyId
    previous_status: HealthStatus
    current_status: HealthStatus
    message: str | None = Field(default=None, min_length=1, max_length=1024)

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str | None) -> str | None:
        return _validate_optional_text(value, field_name="strategy health message")

    @model_validator(mode="after")
    def validate_envelope(self) -> Self:
        _validate_event_type(self.envelope, STRATEGY_HEALTH_CHANGED_EVENT_TYPE)
        _validate_strategy_lineage(
            self.envelope.strategy_id,
            self.strategy_id,
            field_name="strategy_id",
        )
        if self.previous_status is self.current_status:
            msg = "strategy health change requires distinct statuses"
            raise ValueError(msg)
        return self


class OrderBookSnapshotEvent(CanonicalModel):
    envelope: EventEnvelope
    snapshot: OrderBookSnapshot

    @model_validator(mode="after")
    def validate_envelope(self) -> Self:
        _validate_event_type(self.envelope, MARKET_ORDER_BOOK_SNAPSHOT_EVENT_TYPE)
        _validate_market_lineage(
            self.envelope.market_id,
            self.snapshot.market_id,
            field_name="snapshot.market_id",
        )
        _validate_exchange_lineage(
            self.envelope.exchange,
            self.snapshot.exchange,
            field_name="snapshot.exchange",
        )
        return self


class OrderBookDeltaEvent(CanonicalModel):
    envelope: EventEnvelope
    delta: OrderBookDelta

    @model_validator(mode="after")
    def validate_envelope(self) -> Self:
        _validate_event_type(self.envelope, MARKET_ORDER_BOOK_DELTA_EVENT_TYPE)
        _validate_market_lineage(
            self.envelope.market_id,
            self.delta.market_id,
            field_name="delta.market_id",
        )
        _validate_exchange_lineage(
            self.envelope.exchange,
            self.delta.exchange,
            field_name="delta.exchange",
        )
        return self


class TradeObservedEvent(CanonicalModel):
    envelope: EventEnvelope
    trade: Trade

    @model_validator(mode="after")
    def validate_envelope(self) -> Self:
        _validate_event_type(self.envelope, MARKET_TRADE_OBSERVED_EVENT_TYPE)
        _validate_market_lineage(
            self.envelope.market_id,
            self.trade.market_id,
            field_name="trade.market_id",
        )
        _validate_exchange_lineage(
            self.envelope.exchange,
            self.trade.exchange,
            field_name="trade.exchange",
        )
        return self


class SignalGeneratedEvent(CanonicalModel):
    envelope: EventEnvelope
    signal: Signal

    @model_validator(mode="after")
    def validate_envelope(self) -> Self:
        _validate_event_type(self.envelope, STRATEGY_SIGNAL_GENERATED_EVENT_TYPE)
        _validate_strategy_lineage(
            self.envelope.strategy_id,
            self.signal.strategy_id,
            field_name="signal.strategy_id",
        )
        _validate_optional_market_lineage(
            self.envelope.market_id,
            self.signal.market_id,
            field_name="signal.market_id",
        )
        return self


class RiskCheckRequestedEvent(CanonicalModel):
    envelope: EventEnvelope
    intent: OrderIntent
    input_snapshot: RiskInputSnapshot

    @model_validator(mode="after")
    def validate_envelope(self) -> Self:
        _validate_event_type(self.envelope, RISK_CHECK_REQUESTED_EVENT_TYPE)
        _validate_correlation_lineage(self.envelope.correlation_id, self.intent.correlation_id)
        _validate_strategy_lineage(
            self.envelope.strategy_id,
            self.intent.strategy_id,
            field_name="intent.strategy_id",
        )
        _validate_strategy_lineage(
            self.envelope.strategy_id,
            self.input_snapshot.strategy_id,
            field_name="input_snapshot.strategy_id",
        )
        _validate_market_lineage(
            self.envelope.market_id,
            self.intent.market_id,
            field_name="intent.market_id",
        )
        _validate_market_lineage(
            self.envelope.market_id,
            self.input_snapshot.market_id,
            field_name="input_snapshot.market_id",
        )
        _validate_exchange_lineage(
            self.envelope.exchange,
            self.input_snapshot.exchange,
            field_name="input_snapshot.exchange",
        )
        _validate_account_lineage(
            self.envelope.account_id,
            self.input_snapshot.account_id,
            field_name="input_snapshot.account_id",
        )
        return self


class RiskApprovedEvent(CanonicalModel):
    envelope: EventEnvelope
    decision: RiskDecision
    approved_order: ApprovedOrder

    @model_validator(mode="after")
    def validate_envelope(self) -> Self:
        _validate_event_type(self.envelope, RISK_APPROVED_EVENT_TYPE)
        _validate_risk_decision_status(self.decision, RiskDecisionStatus.APPROVED)
        _validate_correlation_lineage(self.envelope.correlation_id, self.decision.correlation_id)
        _validate_approved_order_lineage(self.approved_order, self.decision)
        _validate_strategy_lineage(
            self.envelope.strategy_id,
            self.approved_order.strategy_id,
            field_name="approved_order.strategy_id",
        )
        _validate_market_lineage(
            self.envelope.market_id,
            self.approved_order.market_id,
            field_name="approved_order.market_id",
        )
        _validate_exchange_lineage(
            self.envelope.exchange,
            self.approved_order.exchange,
            field_name="approved_order.exchange",
        )
        _validate_account_lineage(
            self.envelope.account_id,
            self.approved_order.account_id,
            field_name="approved_order.account_id",
        )
        _validate_order_lineage(
            self.envelope.order_id,
            self.approved_order.order_id,
            field_name="approved_order.order_id",
        )
        return self


class RiskRejectedEvent(CanonicalModel):
    envelope: EventEnvelope
    decision: RiskDecision

    @model_validator(mode="after")
    def validate_envelope(self) -> Self:
        _validate_event_type(self.envelope, RISK_REJECTED_EVENT_TYPE)
        _validate_risk_decision_status(self.decision, RiskDecisionStatus.REJECTED)
        _validate_correlation_lineage(self.envelope.correlation_id, self.decision.correlation_id)
        return self


class RiskLimitBreachedEvent(CanonicalModel):
    envelope: EventEnvelope
    breach: RiskBreach

    @model_validator(mode="after")
    def validate_envelope(self) -> Self:
        _validate_event_type(self.envelope, RISK_LIMIT_BREACHED_EVENT_TYPE)
        _validate_correlation_lineage(self.envelope.correlation_id, self.breach.correlation_id)
        return self


class KillSwitchActivatedEvent(CanonicalModel):
    envelope: EventEnvelope
    state: KillSwitchState

    @model_validator(mode="after")
    def validate_envelope(self) -> Self:
        _validate_event_type(self.envelope, RISK_KILL_SWITCH_ACTIVATED_EVENT_TYPE)
        if not self.state.active:
            msg = "kill-switch activated event requires an active kill-switch state"
            raise ValueError(msg)
        return self


class KillSwitchReleasedEvent(CanonicalModel):
    envelope: EventEnvelope
    state: KillSwitchState

    @model_validator(mode="after")
    def validate_envelope(self) -> Self:
        _validate_event_type(self.envelope, RISK_KILL_SWITCH_RELEASED_EVENT_TYPE)
        if self.state.active:
            msg = "kill-switch released event requires an inactive kill-switch state"
            raise ValueError(msg)
        return self


def _validate_event_type(envelope: EventEnvelope, expected_event_type: str) -> None:
    if envelope.event_type != expected_event_type:
        msg = f"event envelope event_type must be {expected_event_type!r}"
        raise ValueError(msg)


def _validate_market_lineage(
    envelope_market_id: MarketId | None,
    payload_market_id: MarketId,
    *,
    field_name: str,
) -> None:
    if envelope_market_id is None:
        msg = "event envelope market_id is required for market events"
        raise ValueError(msg)
    _validate_optional_market_lineage(
        envelope_market_id,
        payload_market_id,
        field_name=field_name,
    )


def _validate_optional_market_lineage(
    envelope_market_id: MarketId | None,
    payload_market_id: MarketId,
    *,
    field_name: str,
) -> None:
    if envelope_market_id is not None and envelope_market_id != payload_market_id:
        msg = f"event envelope market_id must match {field_name} when provided"
        raise ValueError(msg)


def _validate_exchange_lineage(
    envelope_exchange: str | None,
    payload_exchange: str,
    *,
    field_name: str,
) -> None:
    if envelope_exchange is None:
        msg = "event envelope exchange is required for market data events"
        raise ValueError(msg)
    if envelope_exchange != payload_exchange:
        msg = f"event envelope exchange must match {field_name}"
        raise ValueError(msg)


def _validate_account_lineage(
    envelope_account_id: AccountId | None,
    payload_account_id: AccountId,
    *,
    field_name: str,
) -> None:
    if envelope_account_id is None:
        msg = "event envelope account_id is required for account-scoped events"
        raise ValueError(msg)
    if envelope_account_id != payload_account_id:
        msg = f"event envelope account_id must match {field_name}"
        raise ValueError(msg)


def _validate_order_lineage(
    envelope_order_id: OrderId | None,
    payload_order_id: OrderId,
    *,
    field_name: str,
) -> None:
    if envelope_order_id is None:
        msg = "event envelope order_id is required for order-scoped events"
        raise ValueError(msg)
    if envelope_order_id != payload_order_id:
        msg = f"event envelope order_id must match {field_name}"
        raise ValueError(msg)


def _validate_strategy_lineage(
    envelope_strategy_id: StrategyId | None,
    payload_strategy_id: StrategyId,
    *,
    field_name: str,
) -> None:
    if envelope_strategy_id is None:
        msg = "event envelope strategy_id is required for strategy events"
        raise ValueError(msg)
    if envelope_strategy_id != payload_strategy_id:
        msg = f"event envelope strategy_id must match {field_name}"
        raise ValueError(msg)


def _validate_correlation_lineage(
    envelope_correlation_id: CorrelationId,
    payload_correlation_id: CorrelationId,
) -> None:
    if envelope_correlation_id != payload_correlation_id:
        msg = "event envelope correlation_id must match payload correlation_id"
        raise ValueError(msg)


def _validate_risk_decision_status(
    decision: RiskDecision,
    expected_status: RiskDecisionStatus,
) -> None:
    if decision.status is not expected_status:
        msg = f"risk event decision status must be {expected_status.value!r}"
        raise ValueError(msg)


def _validate_approved_order_lineage(
    approved_order: ApprovedOrder,
    decision: RiskDecision,
) -> None:
    if approved_order.risk_decision_id != decision.risk_decision_id:
        msg = "approved_order risk_decision_id must match decision"
        raise ValueError(msg)
    if approved_order.intent_id != decision.intent_id:
        msg = "approved_order intent_id must match decision"
        raise ValueError(msg)
    if approved_order.correlation_id != decision.correlation_id:
        msg = "approved_order correlation_id must match decision"
        raise ValueError(msg)


def _validate_required_text(value: str, *, field_name: str) -> str:
    if value == "" or value.strip() != value:
        msg = f"{field_name} must be nonempty without surrounding whitespace"
        raise ValueError(msg)
    return value


def _validate_optional_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _validate_required_text(value, field_name=field_name)
