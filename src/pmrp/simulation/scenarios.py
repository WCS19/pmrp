"""Deterministic simulation scenario definitions."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType

from pmrp.schemas.market_data import OrderBookDelta, OrderBookSnapshot, Trade
from pmrp.schemas.orders import CancelOrderRequest, Fill, OrderIntent
from pmrp.schemas.serialization import canonical_sha256, to_canonical_data
from pmrp.schemas.simulation import SimulationConfiguration
from pmrp.schemas.time import parse_utc_datetime
from pmrp.simulation.errors import SimulationConfigurationError
from pmrp.simulation.results import SimulationArtifact, SimulationSourceType

SIMULATION_SCENARIO_HASH_VERSION = "simulation_scenario_hash_v1"

_MAX_TEXT_LENGTH = 128

type ScenarioMarketEventPayload = OrderBookSnapshot | OrderBookDelta | Trade
type ScenarioOrderActionPayload = OrderIntent | CancelOrderRequest


@dataclass(frozen=True, slots=True)
class ScheduledMarketEvent:
    """One canonical market-data event scheduled for a scenario."""

    sequence: int
    scheduled_at: datetime
    event: ScenarioMarketEventPayload
    source_type: SimulationSourceType = SimulationSourceType.OBSERVED_FACT

    def __post_init__(self) -> None:
        object.__setattr__(self, "sequence", _validate_sequence(self.sequence))
        object.__setattr__(
            self,
            "scheduled_at",
            parse_utc_datetime(self.scheduled_at),
        )
        if not isinstance(self.event, OrderBookSnapshot | OrderBookDelta | Trade):
            msg = "event must be an OrderBookSnapshot, OrderBookDelta, or Trade"
            raise TypeError(msg)
        _validate_source_type(self.source_type)

    @property
    def event_type(self) -> str:
        """Return a stable market event type label."""

        return _market_event_type(self.event)

    def canonical_payload(self) -> Mapping[str, object]:
        """Return stable JSON-compatible scheduled event data."""

        return {
            "event": to_canonical_data(self.event),
            "event_type": self.event_type,
            "scheduled_at": self.scheduled_at,
            "sequence": self.sequence,
            "source_type": self.source_type,
        }


@dataclass(frozen=True, slots=True)
class ScheduledOrderAction:
    """One order intent or cancel request scheduled for a scenario."""

    sequence: int
    scheduled_at: datetime
    action: ScenarioOrderActionPayload
    source_type: SimulationSourceType = SimulationSourceType.INFERRED_BEHAVIOR

    def __post_init__(self) -> None:
        object.__setattr__(self, "sequence", _validate_sequence(self.sequence))
        object.__setattr__(
            self,
            "scheduled_at",
            parse_utc_datetime(self.scheduled_at),
        )
        if not isinstance(self.action, OrderIntent | CancelOrderRequest):
            msg = "action must be an OrderIntent or CancelOrderRequest"
            raise TypeError(msg)
        _validate_source_type(self.source_type)

    @property
    def action_type(self) -> str:
        """Return a stable order action type label."""

        return _order_action_type(self.action)

    def canonical_payload(self) -> Mapping[str, object]:
        """Return stable JSON-compatible scheduled action data."""

        return {
            "action": to_canonical_data(self.action),
            "action_type": self.action_type,
            "scheduled_at": self.scheduled_at,
            "sequence": self.sequence,
            "source_type": self.source_type,
        }


@dataclass(frozen=True, slots=True)
class ExpectedSimulationFill:
    """One canonical fill expected from a scenario run."""

    sequence: int
    fill: Fill
    source_type: SimulationSourceType = SimulationSourceType.SIMULATED_OUTPUT

    def __post_init__(self) -> None:
        object.__setattr__(self, "sequence", _validate_sequence(self.sequence))
        if not isinstance(self.fill, Fill):
            msg = "fill must be a canonical Fill"
            raise TypeError(msg)
        if self.source_type is not SimulationSourceType.SIMULATED_OUTPUT:
            raise SimulationConfigurationError(
                "Expected simulation fills must be classified as simulated output",
                reason_code="simulation_scenario_expected_fill_source_invalid",
                context={"source_type": str(self.source_type)},
            )

    def canonical_payload(self) -> Mapping[str, object]:
        """Return stable JSON-compatible expected fill data."""

        return {
            "fill": to_canonical_data(self.fill),
            "sequence": self.sequence,
            "source_type": self.source_type,
        }


@dataclass(frozen=True, slots=True)
class SimulationScenario:
    """Immutable deterministic definition for one simulation scenario."""

    scenario_id: str
    name: str
    configuration: SimulationConfiguration
    initial_book: OrderBookSnapshot
    market_events: tuple[ScheduledMarketEvent, ...] = ()
    order_actions: tuple[ScheduledOrderAction, ...] = ()
    expected_fills: tuple[ExpectedSimulationFill, ...] = ()
    expected_final_book: OrderBookSnapshot | None = None
    expected_final_book_source_type: SimulationSourceType | None = None
    tags: tuple[str, ...] = ()
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "scenario_id",
            _validate_text(self.scenario_id, field_name="scenario_id"),
        )
        object.__setattr__(self, "name", _validate_text(self.name, field_name="name"))
        if not isinstance(self.configuration, SimulationConfiguration):
            raise SimulationConfigurationError(
                "Simulation scenario requires a canonical SimulationConfiguration",
                reason_code="simulation_scenario_configuration_invalid",
            )
        _validate_initial_book(self.initial_book)

        market_events = _normalize_market_events(self.market_events)
        order_actions = _normalize_order_actions(self.order_actions)
        expected_fills = _normalize_expected_fills(self.expected_fills)
        expected_final_book = _validate_expected_final_book(
            self.expected_final_book,
            initial_book=self.initial_book,
        )
        expected_final_book_source_type = _validate_expected_final_book_source_type(
            self.expected_final_book_source_type,
            expected_final_book=expected_final_book,
        )

        _validate_market_event_lineage(market_events, initial_book=self.initial_book)
        _validate_order_action_lineage(order_actions, initial_book=self.initial_book)
        _validate_expected_fill_lineage(expected_fills, initial_book=self.initial_book)

        object.__setattr__(self, "market_events", market_events)
        object.__setattr__(self, "order_actions", order_actions)
        object.__setattr__(self, "expected_fills", expected_fills)
        object.__setattr__(self, "expected_final_book", expected_final_book)
        object.__setattr__(
            self,
            "expected_final_book_source_type",
            expected_final_book_source_type,
        )
        object.__setattr__(self, "tags", _normalize_tags(self.tags))
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))

    @property
    def configuration_hash(self) -> str:
        """Return the stable hash of the scenario configuration."""

        return canonical_sha256(self.configuration)

    @property
    def scenario_hash(self) -> str:
        """Return the deterministic hash of the scenario definition."""

        return canonical_sha256(self.canonical_payload())

    @property
    def source_type_counts(self) -> Mapping[SimulationSourceType, int]:
        """Return immutable counts of scenario inputs and outputs by source type."""

        counts: Counter[SimulationSourceType] = Counter({SimulationSourceType.OBSERVED_FACT: 1})
        counts.update(event.source_type for event in self.market_events)
        counts.update(action.source_type for action in self.order_actions)
        counts.update(fill.source_type for fill in self.expected_fills)
        if (
            self.expected_final_book is not None
            and self.expected_final_book_source_type is not None
        ):
            counts.update((self.expected_final_book_source_type,))
        return MappingProxyType(dict(counts))

    def as_result_artifact(self, *, sequence: int) -> SimulationArtifact:
        """Return this scenario as a simulation result artifact."""

        return SimulationArtifact(
            sequence=_validate_sequence(sequence),
            artifact_type="simulation_scenario",
            artifact_id=self.scenario_id,
            artifact_hash=self.scenario_hash,
            source_type=SimulationSourceType.INFERRED_BEHAVIOR,
        )

    def canonical_payload(self) -> Mapping[str, object]:
        """Return stable JSON-compatible scenario data."""

        payload: dict[str, object] = {
            "configuration": to_canonical_data(self.configuration),
            "configuration_hash": self.configuration_hash,
            "expected_fills": [fill.canonical_payload() for fill in self.expected_fills],
            "hash_version": SIMULATION_SCENARIO_HASH_VERSION,
            "initial_book": to_canonical_data(self.initial_book),
            "market_events": [event.canonical_payload() for event in self.market_events],
            "metadata": dict(self.metadata),
            "name": self.name,
            "order_actions": [action.canonical_payload() for action in self.order_actions],
            "scenario_id": self.scenario_id,
            "tags": list(self.tags),
        }
        if self.expected_final_book is not None:
            payload["expected_final_book"] = to_canonical_data(self.expected_final_book)
            payload["expected_final_book_source_type"] = self.expected_final_book_source_type
        return payload


def _market_event_type(event: ScenarioMarketEventPayload) -> str:
    if isinstance(event, OrderBookSnapshot):
        return "order_book_snapshot"
    if isinstance(event, OrderBookDelta):
        return "order_book_delta"
    return "trade"


def _order_action_type(action: ScenarioOrderActionPayload) -> str:
    if isinstance(action, OrderIntent):
        return "order_intent"
    return "cancel_order_request"


def _validate_sequence(sequence: int) -> int:
    if type(sequence) is not int:
        msg = "sequence must be an integer"
        raise TypeError(msg)
    if sequence < 0:
        msg = "sequence must be nonnegative"
        raise ValueError(msg)
    return sequence


def _validate_source_type(source_type: SimulationSourceType) -> None:
    if not isinstance(source_type, SimulationSourceType):
        msg = "source_type must be a SimulationSourceType"
        raise TypeError(msg)


def _validate_text(value: str, *, field_name: str, max_length: int = _MAX_TEXT_LENGTH) -> str:
    if type(value) is not str:
        msg = f"{field_name} must be a string"
        raise TypeError(msg)
    if value == "" or value.strip() != value:
        msg = f"{field_name} must be nonempty without surrounding whitespace"
        raise ValueError(msg)
    if len(value) > max_length:
        msg = f"{field_name} must be at most {max_length} characters"
        raise ValueError(msg)
    return value


def _validate_initial_book(initial_book: OrderBookSnapshot) -> None:
    if not isinstance(initial_book, OrderBookSnapshot):
        raise SimulationConfigurationError(
            "Simulation scenario initial_book must be an OrderBookSnapshot",
            reason_code="simulation_scenario_initial_book_invalid",
        )
    if not initial_book.is_valid:
        raise SimulationConfigurationError(
            "Simulation scenario initial_book must be valid",
            reason_code="simulation_scenario_initial_book_invalid",
            context={"market_id": str(initial_book.market_id)},
        )


def _validate_expected_final_book(
    expected_final_book: OrderBookSnapshot | None,
    *,
    initial_book: OrderBookSnapshot,
) -> OrderBookSnapshot | None:
    if expected_final_book is None:
        return None
    if not isinstance(expected_final_book, OrderBookSnapshot):
        raise SimulationConfigurationError(
            "Simulation scenario expected_final_book must be an OrderBookSnapshot",
            reason_code="simulation_scenario_expected_final_book_invalid",
        )
    if not expected_final_book.is_valid:
        raise SimulationConfigurationError(
            "Simulation scenario expected_final_book must be valid",
            reason_code="simulation_scenario_expected_final_book_invalid",
            context={"market_id": str(expected_final_book.market_id)},
        )
    _validate_book_lineage(
        expected_final_book,
        initial_book=initial_book,
        reason_code="simulation_scenario_expected_final_book_mismatch",
    )
    return expected_final_book


def _validate_expected_final_book_source_type(
    source_type: SimulationSourceType | None,
    *,
    expected_final_book: OrderBookSnapshot | None,
) -> SimulationSourceType | None:
    if expected_final_book is None:
        if source_type is not None:
            raise SimulationConfigurationError(
                "Expected final book source type requires expected_final_book",
                reason_code="simulation_scenario_expected_final_book_source_invalid",
                context={"source_type": str(source_type)},
            )
        return None
    if source_type is None:
        return SimulationSourceType.SIMULATED_OUTPUT
    if source_type is not SimulationSourceType.SIMULATED_OUTPUT:
        raise SimulationConfigurationError(
            "Expected final book must be classified as simulated output",
            reason_code="simulation_scenario_expected_final_book_source_invalid",
            context={"source_type": str(source_type)},
        )
    return source_type


def _normalize_market_events(
    events: tuple[ScheduledMarketEvent, ...],
) -> tuple[ScheduledMarketEvent, ...]:
    if not isinstance(events, tuple):
        msg = "market_events must be a tuple"
        raise TypeError(msg)
    if any(not isinstance(event, ScheduledMarketEvent) for event in events):
        msg = "market_events must contain only ScheduledMarketEvent values"
        raise TypeError(msg)
    return _sort_and_validate_unique_sequences(events, field_name="market_events")


def _normalize_order_actions(
    actions: tuple[ScheduledOrderAction, ...],
) -> tuple[ScheduledOrderAction, ...]:
    if not isinstance(actions, tuple):
        msg = "order_actions must be a tuple"
        raise TypeError(msg)
    if any(not isinstance(action, ScheduledOrderAction) for action in actions):
        msg = "order_actions must contain only ScheduledOrderAction values"
        raise TypeError(msg)
    return _sort_and_validate_unique_sequences(actions, field_name="order_actions")


def _normalize_expected_fills(
    fills: tuple[ExpectedSimulationFill, ...],
) -> tuple[ExpectedSimulationFill, ...]:
    if not isinstance(fills, tuple):
        msg = "expected_fills must be a tuple"
        raise TypeError(msg)
    if any(not isinstance(fill, ExpectedSimulationFill) for fill in fills):
        msg = "expected_fills must contain only ExpectedSimulationFill values"
        raise TypeError(msg)
    return _sort_and_validate_unique_sequences(fills, field_name="expected_fills")


def _sort_and_validate_unique_sequences[
    T: ScheduledMarketEvent | ScheduledOrderAction | ExpectedSimulationFill,
](items: tuple[T, ...], *, field_name: str) -> tuple[T, ...]:
    sorted_items = tuple(sorted(items, key=lambda item: item.sequence))
    sequences = [item.sequence for item in sorted_items]
    if len(set(sequences)) != len(sequences):
        raise SimulationConfigurationError(
            f"{field_name} must have unique sequences",
            reason_code="simulation_scenario_sequence_duplicate",
            context={"field_name": field_name},
        )
    return sorted_items


def _normalize_tags(tags: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(tags, tuple):
        msg = "tags must be a tuple"
        raise TypeError(msg)
    normalized = tuple(
        sorted(_validate_text(tag, field_name="tag", max_length=_MAX_TEXT_LENGTH) for tag in tags)
    )
    if len(set(normalized)) != len(normalized):
        raise SimulationConfigurationError(
            "Simulation scenario tags must be unique",
            reason_code="simulation_scenario_tag_duplicate",
        )
    return normalized


def _freeze_metadata(metadata: Mapping[str, str]) -> Mapping[str, str]:
    if not isinstance(metadata, Mapping):
        msg = "metadata must be a mapping"
        raise TypeError(msg)
    frozen: dict[str, str] = {}
    for key, value in metadata.items():
        frozen[_validate_text(key, field_name="metadata key")] = _validate_text(
            value,
            field_name=f"metadata value for {key}",
        )
    return MappingProxyType(frozen)


def _validate_market_event_lineage(
    events: tuple[ScheduledMarketEvent, ...],
    *,
    initial_book: OrderBookSnapshot,
) -> None:
    for event in events:
        if isinstance(event.event, OrderBookSnapshot | OrderBookDelta):
            _validate_book_lineage(
                event.event,
                initial_book=initial_book,
                reason_code="simulation_scenario_market_event_mismatch",
            )
            continue
        _validate_trade_lineage(event.event, initial_book=initial_book)


def _validate_order_action_lineage(
    actions: tuple[ScheduledOrderAction, ...],
    *,
    initial_book: OrderBookSnapshot,
) -> None:
    for action in actions:
        if isinstance(action.action, OrderIntent):
            if (
                action.action.market_id != initial_book.market_id
                or action.action.contract_id != initial_book.contract_id
            ):
                raise SimulationConfigurationError(
                    "Simulation scenario order intent does not match initial book",
                    reason_code="simulation_scenario_order_action_mismatch",
                    context={"action_type": action.action_type},
                )
            continue
        if action.action.exchange != initial_book.exchange:
            raise SimulationConfigurationError(
                "Simulation scenario cancel request exchange does not match initial book",
                reason_code="simulation_scenario_order_action_mismatch",
                context={"action_type": action.action_type},
            )


def _validate_expected_fill_lineage(
    expected_fills: tuple[ExpectedSimulationFill, ...],
    *,
    initial_book: OrderBookSnapshot,
) -> None:
    for expected_fill in expected_fills:
        fill = expected_fill.fill
        if (
            fill.market_id != initial_book.market_id
            or fill.contract_id != initial_book.contract_id
            or fill.exchange != initial_book.exchange
        ):
            raise SimulationConfigurationError(
                "Simulation scenario expected fill does not match initial book",
                reason_code="simulation_scenario_expected_fill_mismatch",
                context={"fill_id": str(fill.fill_id)},
            )


def _validate_book_lineage(
    book: OrderBookSnapshot | OrderBookDelta,
    *,
    initial_book: OrderBookSnapshot,
    reason_code: str,
) -> None:
    if (
        book.market_id != initial_book.market_id
        or book.contract_id != initial_book.contract_id
        or book.exchange != initial_book.exchange
    ):
        raise SimulationConfigurationError(
            "Simulation scenario order-book lineage does not match initial book",
            reason_code=reason_code,
            context={"market_id": str(book.market_id), "contract_id": str(book.contract_id)},
        )


def _validate_trade_lineage(trade: Trade, *, initial_book: OrderBookSnapshot) -> None:
    if (
        trade.market_id != initial_book.market_id
        or trade.contract_id != initial_book.contract_id
        or trade.exchange != initial_book.exchange
    ):
        raise SimulationConfigurationError(
            "Simulation scenario trade lineage does not match initial book",
            reason_code="simulation_scenario_market_event_mismatch",
            context={"trade_id": trade.trade_id},
        )
