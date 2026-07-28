from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

import pytest

from pmrp.clock import FrozenClock
from pmrp.events import (
    DeterministicEventIdentifierGenerator,
    EventFactory,
    EventTypeRegistration,
    EventTypeRegistry,
    PrefixedUlidIdentifierGenerator,
    UnknownEventTypeError,
)
from pmrp.schemas.enums import DataQualityFlag
from pmrp.schemas.identifiers import CorrelationId, EventId
from pmrp.schemas.serialization import canonical_sha256

pytestmark = pytest.mark.unit


def _instant() -> datetime:
    return datetime(2026, 7, 28, 19, 0, tzinfo=UTC)


def _registry() -> EventTypeRegistry:
    return EventTypeRegistry(
        (
            EventTypeRegistration(
                event_type="order.created",
                schema_name="event_envelope",
                schema_version=7,
            ),
        )
    )


def _factory() -> EventFactory:
    return EventFactory(
        clock=FrozenClock(_instant()),
        registry=_registry(),
        identifier_generator=DeterministicEventIdentifierGenerator(),
    )


def test_event_factory_creates_envelope_with_clock_timestamp_and_registered_version() -> None:
    event = _factory().create_envelope(event_type="order.created", producer="execution")

    assert event.event_id == EventId("evt_test_000000000000000000000001")
    assert event.correlation_id == CorrelationId("corr_test_000000000000000000000001")
    assert event.schema_version == 7
    assert event.occurred_at == _instant()
    assert event.received_at == _instant()
    assert event.published_at == _instant()
    assert event.producer == "execution"


def test_event_factory_uses_supplied_occurrence_receipt_and_lineage_fields() -> None:
    event = _factory().create_envelope(
        event_type="order.created",
        producer="normalizer",
        occurred_at=_instant() - timedelta(seconds=2),
        received_at=_instant() - timedelta(seconds=1),
        exchange="kalshi",
        market_id="mkt_01j00000000000000000000000",
        account_id="acct_shadow",
        strategy_id="strat_example",
        order_id="ord_01j00000000000000000000000",
        correlation_id="corr_01j00000000000000000000000",
        causation_id="cmd_01j00000000000000000000000",
        trace_id="trace-abc123",
        replay_session_id="rpl_01j00000000000000000000000",
        simulation_session_id="sim_01j00000000000000000000000",
        quality_flags=(DataQualityFlag.REPLAYED,),
        attributes={"nested": {"level": "one"}},
    )
    nested_attributes = event.attributes["nested"]

    assert event.occurred_at == _instant() - timedelta(seconds=2)
    assert event.received_at == _instant() - timedelta(seconds=1)
    assert event.published_at == _instant()
    assert event.correlation_id == "corr_01j00000000000000000000000"
    assert event.causation_id == "cmd_01j00000000000000000000000"
    assert event.quality_flags == (DataQualityFlag.REPLAYED,)
    assert isinstance(nested_attributes, Mapping)


def test_event_factory_generates_distinct_event_and_correlation_ids() -> None:
    factory = _factory()

    first = factory.create_envelope(event_type="order.created", producer="execution")
    second = factory.create_envelope(event_type="order.created", producer="execution")

    assert first.event_id != second.event_id
    assert first.correlation_id != second.correlation_id


def test_event_factory_rejects_unknown_event_type() -> None:
    with pytest.raises(UnknownEventTypeError, match="not registered"):
        _factory().create_envelope(event_type="order.cancelled", producer="execution")


def test_event_factory_rejects_noncanonical_attributes() -> None:
    with pytest.raises(TypeError, match="must not contain floats"):
        _factory().create_envelope(
            event_type="order.created",
            producer="execution",
            attributes={"probability": 0.5},
        )


def test_event_factory_attributes_cannot_mutate_stable_hash() -> None:
    event = _factory().create_envelope(
        event_type="order.created",
        producer="execution",
        attributes={"source": "unit_test"},
    )
    original_hash = canonical_sha256(event)

    with pytest.raises(TypeError, match="does not support item assignment"):
        event.attributes["source"] = "changed"

    assert canonical_sha256(event) == original_hash


def test_prefixed_ulid_identifier_generator_uses_expected_identifier_shapes() -> None:
    generator = PrefixedUlidIdentifierGenerator()

    event_id = generator.event_id(_instant())
    correlation_id = generator.correlation_id(_instant())

    assert event_id.startswith("evt_")
    assert correlation_id.startswith("corr_")
    assert len(event_id.removeprefix("evt_")) == 26
    assert len(correlation_id.removeprefix("corr_")) == 26


def test_prefixed_ulid_identifier_generator_rejects_naive_timestamp() -> None:
    generator = PrefixedUlidIdentifierGenerator()

    with pytest.raises(ValueError, match="timezone-aware"):
        generator.event_id(datetime.fromisoformat("2026-07-28T19:00:00"))
