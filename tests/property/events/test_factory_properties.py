from datetime import UTC, datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.clock import FrozenClock
from pmrp.events import (
    DeterministicEventIdentifierGenerator,
    EventFactory,
    EventTypeRegistration,
    EventTypeRegistry,
)

pytestmark = pytest.mark.property

_COUNT = st.integers(min_value=1, max_value=100)


@given(count=_COUNT)
def test_event_factory_generates_unique_deterministic_ids_for_generated_event_counts(
    count: int,
) -> None:
    registry = EventTypeRegistry(
        (
            EventTypeRegistration(
                event_type="order.created",
                schema_name="event_envelope",
                schema_version=1,
            ),
        )
    )
    factory = EventFactory(
        clock=FrozenClock(datetime(2026, 7, 28, 19, 0, tzinfo=UTC)),
        registry=registry,
        identifier_generator=DeterministicEventIdentifierGenerator(),
    )

    events = tuple(
        factory.create_envelope(event_type="order.created", producer="execution")
        for _ in range(count)
    )

    assert len({event.event_id for event in events}) == count
    assert len({event.correlation_id for event in events}) == count
    assert events[-1].event_id.endswith(f"{count:024d}")
