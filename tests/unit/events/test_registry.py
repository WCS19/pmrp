import pytest

from pmrp.events import EventTypeRegistration, EventTypeRegistry, UnknownEventTypeError

pytestmark = pytest.mark.unit


def test_event_type_registry_returns_registered_schema_version() -> None:
    registry = EventTypeRegistry(
        (
            EventTypeRegistration(
                event_type="order.created",
                schema_name="event_envelope",
                schema_version=3,
            ),
        )
    )

    assert registry.schema_version_for("order.created") == 3
    assert registry.get("order.created").schema_name == "event_envelope"


def test_event_type_registry_rejects_duplicate_event_type() -> None:
    registry = EventTypeRegistry(
        (
            EventTypeRegistration(
                event_type="order.created",
                schema_name="event_envelope",
                schema_version=1,
            ),
        )
    )

    with pytest.raises(ValueError, match="already registered"):
        registry.register(
            EventTypeRegistration(
                event_type="order.created",
                schema_name="event_envelope",
                schema_version=1,
            )
        )


def test_event_type_registry_rejects_unknown_event_type() -> None:
    registry = EventTypeRegistry()

    with pytest.raises(UnknownEventTypeError, match="not registered"):
        registry.schema_version_for("order.created")


def test_event_type_registration_rejects_invalid_event_type() -> None:
    with pytest.raises(ValueError, match="dotted lowercase"):
        EventTypeRegistration(
            event_type="OrderCreated",
            schema_name="event_envelope",
            schema_version=1,
        )


def test_event_type_registration_rejects_invalid_schema_name() -> None:
    with pytest.raises(ValueError, match="lowercase snake_case"):
        EventTypeRegistration(
            event_type="order.created",
            schema_name="EventEnvelope",
            schema_version=1,
        )


def test_event_type_registration_rejects_nonpositive_schema_version() -> None:
    with pytest.raises(ValueError, match="positive"):
        EventTypeRegistration(
            event_type="order.created",
            schema_name="event_envelope",
            schema_version=0,
        )
