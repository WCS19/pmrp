"""Schema version validation and the initial schema registry."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from typing import Annotated

from pydantic import BeforeValidator, Field

from pmrp.schemas.base import CanonicalModel


def parse_schema_version(value: object) -> int:
    if isinstance(value, bool):
        msg = "schema version must be a positive integer"
        raise TypeError(msg)
    if not isinstance(value, int):
        msg = "schema version must be a positive integer"
        raise TypeError(msg)
    if value < 1:
        msg = "schema version must be positive"
        raise ValueError(msg)
    return value


type SchemaVersion = Annotated[
    int,
    BeforeValidator(parse_schema_version),
    Field(ge=1),
]


class SchemaCategory(StrEnum):
    COMMAND = "command"
    DOMAIN = "domain"
    EVENT = "event"
    VALUE_OBJECT = "value_object"
    METADATA = "metadata"
    REGISTRY = "registry"


class SchemaRegistration(CanonicalModel):
    schema_name: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    schema_version: SchemaVersion
    schema_category: SchemaCategory
    model_path: str = Field(min_length=1)


@dataclass(frozen=True, slots=True)
class RegisteredSchema:
    schema_name: str
    schema_version: int
    schema_category: SchemaCategory
    model: type[CanonicalModel]

    def as_registration(self) -> SchemaRegistration:
        return SchemaRegistration(
            schema_name=self.schema_name,
            schema_version=self.schema_version,
            schema_category=self.schema_category,
            model_path=f"{self.model.__module__}.{self.model.__qualname__}",
        )


@cache
def _registered_schemas() -> tuple[RegisteredSchema, ...]:
    from pmrp.schemas.commands import CommandEnvelope
    from pmrp.schemas.events import (
        EventEnvelope,
        KillSwitchActivatedEvent,
        KillSwitchReleasedEvent,
        OrderBookDeltaEvent,
        OrderBookSnapshotEvent,
        RiskApprovedEvent,
        RiskLimitBreachedEvent,
        RiskRejectedEvent,
        SignalGeneratedEvent,
        StrategyHealthChangedEvent,
        StrategyStartedEvent,
        StrategyStoppedEvent,
        TradeObservedEvent,
    )
    from pmrp.schemas.market_data import OrderBookDelta, OrderBookSnapshot, Trade
    from pmrp.schemas.markets import Contract, Market, Outcome
    from pmrp.schemas.metadata import (
        AuditMetadata,
        FlexibleMetadata,
        SourceMetadata,
        VersionMetadata,
    )
    from pmrp.schemas.numeric import Money, Price, Probability, Quantity
    from pmrp.schemas.orders import (
        ApprovedOrder,
        CancelOrderAcknowledgement,
        CancelOrderRequest,
        ExchangeOrderAcknowledgement,
        ExchangeOrderRequest,
        Fill,
        OpenOrderSnapshot,
        Order,
        OrderIntent,
        OrderStateTransition,
        ReplaceOrderRequest,
    )
    from pmrp.schemas.portfolio import (
        AccountingJournalEntry,
        CashBalance,
        JournalLine,
        PnlAttribution,
        PortfolioSnapshot,
        Position,
        PositionLot,
        ReconciliationMismatch,
        ReconciliationResult,
        Settlement,
    )
    from pmrp.schemas.replay import ReplayManifest, ReplayResult, ReplaySession
    from pmrp.schemas.risk import (
        KillSwitchState,
        RiskBreach,
        RiskDecision,
        RiskLimit,
        RiskRuleResult,
    )
    from pmrp.schemas.simulation import SimulationConfiguration
    from pmrp.schemas.strategy import (
        Signal,
        StrategyConfigurationRecord,
        StrategyDefinition,
        StrategyInstance,
    )
    from pmrp.schemas.system import (
        AdapterHealth,
        DependencyHealth,
        RateLimitStatus,
        RateLimitWindow,
        ServiceHealth,
    )

    return (
        RegisteredSchema("price", 1, SchemaCategory.VALUE_OBJECT, Price),
        RegisteredSchema("probability", 1, SchemaCategory.VALUE_OBJECT, Probability),
        RegisteredSchema("quantity", 1, SchemaCategory.VALUE_OBJECT, Quantity),
        RegisteredSchema("money", 1, SchemaCategory.VALUE_OBJECT, Money),
        RegisteredSchema("source_metadata", 1, SchemaCategory.METADATA, SourceMetadata),
        RegisteredSchema("version_metadata", 1, SchemaCategory.METADATA, VersionMetadata),
        RegisteredSchema("audit_metadata", 1, SchemaCategory.METADATA, AuditMetadata),
        RegisteredSchema("flexible_metadata", 1, SchemaCategory.METADATA, FlexibleMetadata),
        RegisteredSchema("schema_registration", 1, SchemaCategory.REGISTRY, SchemaRegistration),
        RegisteredSchema("command_envelope", 1, SchemaCategory.COMMAND, CommandEnvelope),
        RegisteredSchema("event_envelope", 1, SchemaCategory.EVENT, EventEnvelope),
        RegisteredSchema("market", 1, SchemaCategory.DOMAIN, Market),
        RegisteredSchema("outcome", 1, SchemaCategory.DOMAIN, Outcome),
        RegisteredSchema("contract", 1, SchemaCategory.DOMAIN, Contract),
        RegisteredSchema("order_book_snapshot", 1, SchemaCategory.DOMAIN, OrderBookSnapshot),
        RegisteredSchema("order_book_delta", 1, SchemaCategory.DOMAIN, OrderBookDelta),
        RegisteredSchema("trade", 1, SchemaCategory.DOMAIN, Trade),
        RegisteredSchema(
            "order_book_snapshot_event",
            1,
            SchemaCategory.EVENT,
            OrderBookSnapshotEvent,
        ),
        RegisteredSchema("order_book_delta_event", 1, SchemaCategory.EVENT, OrderBookDeltaEvent),
        RegisteredSchema("trade_observed_event", 1, SchemaCategory.EVENT, TradeObservedEvent),
        RegisteredSchema("order_intent", 1, SchemaCategory.DOMAIN, OrderIntent),
        RegisteredSchema("approved_order", 1, SchemaCategory.DOMAIN, ApprovedOrder),
        RegisteredSchema("order", 1, SchemaCategory.DOMAIN, Order),
        RegisteredSchema(
            "exchange_order_request",
            1,
            SchemaCategory.COMMAND,
            ExchangeOrderRequest,
        ),
        RegisteredSchema(
            "exchange_order_acknowledgement",
            1,
            SchemaCategory.DOMAIN,
            ExchangeOrderAcknowledgement,
        ),
        RegisteredSchema("cancel_order_request", 1, SchemaCategory.COMMAND, CancelOrderRequest),
        RegisteredSchema(
            "cancel_order_acknowledgement",
            1,
            SchemaCategory.DOMAIN,
            CancelOrderAcknowledgement,
        ),
        RegisteredSchema("replace_order_request", 1, SchemaCategory.COMMAND, ReplaceOrderRequest),
        RegisteredSchema("fill", 1, SchemaCategory.DOMAIN, Fill),
        RegisteredSchema(
            "order_state_transition",
            1,
            SchemaCategory.DOMAIN,
            OrderStateTransition,
        ),
        RegisteredSchema("open_order_snapshot", 1, SchemaCategory.DOMAIN, OpenOrderSnapshot),
        RegisteredSchema("strategy_definition", 1, SchemaCategory.DOMAIN, StrategyDefinition),
        RegisteredSchema("strategy_instance", 1, SchemaCategory.DOMAIN, StrategyInstance),
        RegisteredSchema(
            "strategy_configuration_record",
            1,
            SchemaCategory.DOMAIN,
            StrategyConfigurationRecord,
        ),
        RegisteredSchema("signal", 1, SchemaCategory.DOMAIN, Signal),
        RegisteredSchema("strategy_started_event", 1, SchemaCategory.EVENT, StrategyStartedEvent),
        RegisteredSchema("strategy_stopped_event", 1, SchemaCategory.EVENT, StrategyStoppedEvent),
        RegisteredSchema(
            "strategy_health_changed_event",
            1,
            SchemaCategory.EVENT,
            StrategyHealthChangedEvent,
        ),
        RegisteredSchema("signal_generated_event", 1, SchemaCategory.EVENT, SignalGeneratedEvent),
        RegisteredSchema("risk_limit", 1, SchemaCategory.DOMAIN, RiskLimit),
        RegisteredSchema("risk_rule_result", 1, SchemaCategory.DOMAIN, RiskRuleResult),
        RegisteredSchema("risk_decision", 1, SchemaCategory.DOMAIN, RiskDecision),
        RegisteredSchema("risk_breach", 1, SchemaCategory.DOMAIN, RiskBreach),
        RegisteredSchema("kill_switch_state", 1, SchemaCategory.DOMAIN, KillSwitchState),
        RegisteredSchema("risk_approved_event", 1, SchemaCategory.EVENT, RiskApprovedEvent),
        RegisteredSchema("risk_rejected_event", 1, SchemaCategory.EVENT, RiskRejectedEvent),
        RegisteredSchema(
            "risk_limit_breached_event",
            1,
            SchemaCategory.EVENT,
            RiskLimitBreachedEvent,
        ),
        RegisteredSchema(
            "kill_switch_activated_event",
            1,
            SchemaCategory.EVENT,
            KillSwitchActivatedEvent,
        ),
        RegisteredSchema(
            "kill_switch_released_event",
            1,
            SchemaCategory.EVENT,
            KillSwitchReleasedEvent,
        ),
        RegisteredSchema("position", 1, SchemaCategory.DOMAIN, Position),
        RegisteredSchema("position_lot", 1, SchemaCategory.DOMAIN, PositionLot),
        RegisteredSchema("cash_balance", 1, SchemaCategory.DOMAIN, CashBalance),
        RegisteredSchema("portfolio_snapshot", 1, SchemaCategory.DOMAIN, PortfolioSnapshot),
        RegisteredSchema("journal_line", 1, SchemaCategory.DOMAIN, JournalLine),
        RegisteredSchema(
            "accounting_journal_entry",
            1,
            SchemaCategory.DOMAIN,
            AccountingJournalEntry,
        ),
        RegisteredSchema("pnl_attribution", 1, SchemaCategory.DOMAIN, PnlAttribution),
        RegisteredSchema("settlement", 1, SchemaCategory.DOMAIN, Settlement),
        RegisteredSchema(
            "reconciliation_mismatch",
            1,
            SchemaCategory.DOMAIN,
            ReconciliationMismatch,
        ),
        RegisteredSchema(
            "reconciliation_result",
            1,
            SchemaCategory.DOMAIN,
            ReconciliationResult,
        ),
        RegisteredSchema("replay_manifest", 1, SchemaCategory.DOMAIN, ReplayManifest),
        RegisteredSchema("replay_session", 1, SchemaCategory.DOMAIN, ReplaySession),
        RegisteredSchema("replay_result", 1, SchemaCategory.DOMAIN, ReplayResult),
        RegisteredSchema(
            "simulation_configuration",
            1,
            SchemaCategory.DOMAIN,
            SimulationConfiguration,
        ),
        RegisteredSchema("dependency_health", 1, SchemaCategory.DOMAIN, DependencyHealth),
        RegisteredSchema("service_health", 1, SchemaCategory.DOMAIN, ServiceHealth),
        RegisteredSchema("adapter_health", 1, SchemaCategory.DOMAIN, AdapterHealth),
        RegisteredSchema("rate_limit_window", 1, SchemaCategory.DOMAIN, RateLimitWindow),
        RegisteredSchema("rate_limit_status", 1, SchemaCategory.DOMAIN, RateLimitStatus),
    )


def list_schema_registrations() -> tuple[SchemaRegistration, ...]:
    return tuple(schema.as_registration() for schema in _registered_schemas())


def get_schema_registration(schema_name: str, schema_version: int = 1) -> SchemaRegistration:
    registered_schema = _lookup_registered_schema(schema_name, schema_version)
    return registered_schema.as_registration()


def get_schema_model(schema_name: str, schema_version: int = 1) -> type[CanonicalModel]:
    return _lookup_registered_schema(schema_name, schema_version).model


def schema_json_schema(schema_name: str, schema_version: int = 1) -> dict[str, object]:
    model = get_schema_model(schema_name, schema_version)
    return model.model_json_schema()


def _lookup_registered_schema(schema_name: str, schema_version: int) -> RegisteredSchema:
    version = parse_schema_version(schema_version)
    for registered_schema in _registered_schemas():
        if (
            registered_schema.schema_name == schema_name
            and registered_schema.schema_version == version
        ):
            return registered_schema
    msg = f"schema is not registered: {schema_name} v{version}"
    raise KeyError(msg)
