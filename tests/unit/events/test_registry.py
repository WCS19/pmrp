import pytest

from pmrp.events import (
    EventTypeRegistration,
    EventTypeRegistry,
    UnknownEventTypeError,
    default_event_type_registrations,
    default_event_type_registry,
)
from pmrp.schemas.events import (
    MARKET_ORDER_BOOK_DELTA_EVENT_TYPE,
    MARKET_ORDER_BOOK_SNAPSHOT_EVENT_TYPE,
    MARKET_TRADE_OBSERVED_EVENT_TYPE,
    RISK_APPROVED_EVENT_TYPE,
    RISK_CHECK_REQUESTED_EVENT_TYPE,
    RISK_KILL_SWITCH_ACTIVATED_EVENT_TYPE,
    RISK_KILL_SWITCH_RELEASED_EVENT_TYPE,
    RISK_LIMIT_BREACHED_EVENT_TYPE,
    RISK_REJECTED_EVENT_TYPE,
    STRATEGY_HEALTH_CHANGED_EVENT_TYPE,
    STRATEGY_SIGNAL_GENERATED_EVENT_TYPE,
    STRATEGY_STARTED_EVENT_TYPE,
    STRATEGY_STOPPED_EVENT_TYPE,
)

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


def test_default_event_type_registrations_cover_implemented_canonical_events() -> None:
    registrations = default_event_type_registrations()
    by_event_type = {registration.event_type: registration for registration in registrations}

    assert set(by_event_type) == {
        MARKET_ORDER_BOOK_SNAPSHOT_EVENT_TYPE,
        MARKET_ORDER_BOOK_DELTA_EVENT_TYPE,
        MARKET_TRADE_OBSERVED_EVENT_TYPE,
        STRATEGY_STARTED_EVENT_TYPE,
        STRATEGY_STOPPED_EVENT_TYPE,
        STRATEGY_HEALTH_CHANGED_EVENT_TYPE,
        STRATEGY_SIGNAL_GENERATED_EVENT_TYPE,
        RISK_CHECK_REQUESTED_EVENT_TYPE,
        RISK_APPROVED_EVENT_TYPE,
        RISK_REJECTED_EVENT_TYPE,
        RISK_LIMIT_BREACHED_EVENT_TYPE,
        RISK_KILL_SWITCH_ACTIVATED_EVENT_TYPE,
        RISK_KILL_SWITCH_RELEASED_EVENT_TYPE,
    }
    assert by_event_type[RISK_CHECK_REQUESTED_EVENT_TYPE].schema_name == (
        "risk_check_requested_event"
    )
    assert by_event_type[RISK_APPROVED_EVENT_TYPE].schema_name == "risk_approved_event"
    assert all(registration.schema_version == 1 for registration in registrations)


def test_default_event_type_registry_returns_fresh_mutable_registry() -> None:
    first = default_event_type_registry()
    second = default_event_type_registry()

    first.register(
        EventTypeRegistration(
            event_type="custom.test_event",
            schema_name="event_envelope",
            schema_version=1,
        )
    )

    assert first.schema_version_for(RISK_CHECK_REQUESTED_EVENT_TYPE) == 1
    with pytest.raises(UnknownEventTypeError):
        second.schema_version_for("custom.test_event")


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
