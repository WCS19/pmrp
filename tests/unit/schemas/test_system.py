from datetime import datetime

import pytest
from pydantic import ValidationError

from pmrp.schemas.enums import Environment, HealthStatus
from pmrp.schemas.serialization import canonical_json, canonical_sha256
from pmrp.schemas.system import (
    AdapterHealth,
    DependencyHealth,
    RateLimitStatus,
    RateLimitWindow,
    ServiceHealth,
)
from pmrp.schemas.versions import get_schema_model, get_schema_registration

pytestmark = pytest.mark.unit


def _dependency_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "dependency": "canonical_event_bus",
        "status": HealthStatus.HEALTHY,
        "message": "Processing within bounds.",
        "checked_at": "2026-07-28T19:15:00Z",
    }
    payload.update(overrides)
    return payload


def _service_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "service": "pmrp-api",
        "component": "operator-api",
        "environment": Environment.DEVELOPMENT,
        "status": HealthStatus.DEGRADED,
        "since": "2026-07-28T19:00:00Z",
        "summary": "Operator API is alive with degraded dependency latency.",
        "last_success_at": "2026-07-28T19:14:00Z",
        "last_error_at": "2026-07-28T19:10:00Z",
        "dependencies": (_dependency_payload(),),
        "trading_impact": "strategy_only",
        "ready": True,
        "alive": True,
    }
    payload.update(overrides)
    return payload


def _adapter_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "exchange": "kalshi",
        "environment": Environment.TEST,
        "status": HealthStatus.HEALTHY,
        "connected": True,
        "authenticated": True,
        "subscriptions_active": True,
        "last_message_at": "2026-07-28T19:15:00Z",
        "last_heartbeat_at": "2026-07-28T19:14:59Z",
        "last_reconciliation_at": "2026-07-28T19:00:00Z",
        "market_data_fresh": True,
        "trading_gate_open": False,
        "reconnect_attempts": 0,
        "message": "Connected.",
    }
    payload.update(overrides)
    return payload


def _rate_limit_window_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "orders",
        "limit": 100,
        "remaining": 42,
        "resets_at": "2026-07-28T19:16:00Z",
        "window_seconds": 60,
    }
    payload.update(overrides)
    return payload


def _rate_limit_status_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "exchange": "kalshi",
        "measured_at": "2026-07-28T19:15:00Z",
        "windows": (_rate_limit_window_payload(),),
    }
    payload.update(overrides)
    return payload


def test_dependency_health_accepts_valid_payload() -> None:
    health = DependencyHealth.model_validate(_dependency_payload())

    assert health.dependency == "canonical_event_bus"
    assert health.status is HealthStatus.HEALTHY


def test_service_health_accepts_valid_payload() -> None:
    health = ServiceHealth.model_validate(_service_payload())

    assert health.service == "pmrp-api"
    assert health.environment is Environment.DEVELOPMENT
    assert health.status is HealthStatus.DEGRADED
    assert health.dependencies[0].dependency == "canonical_event_bus"


def test_adapter_health_accepts_valid_payload() -> None:
    health = AdapterHealth.model_validate(_adapter_payload())

    assert health.exchange == "kalshi"
    assert health.status is HealthStatus.HEALTHY
    assert health.reconnect_attempts == 0


def test_rate_limit_status_accepts_valid_payload() -> None:
    status = RateLimitStatus.model_validate(_rate_limit_status_payload())

    assert status.exchange == "kalshi"
    assert status.windows[0].name == "orders"
    assert status.windows[0].remaining == 42


def test_dependency_health_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        DependencyHealth.model_validate(_dependency_payload(unexpected=True))


def test_service_health_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ServiceHealth.model_validate(_service_payload(unexpected=True))


def test_adapter_health_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        AdapterHealth.model_validate(_adapter_payload(unexpected=True))


def test_rate_limit_status_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RateLimitStatus.model_validate(_rate_limit_status_payload(unexpected=True))


def test_dependency_health_rejects_blank_dependency_name() -> None:
    with pytest.raises(ValidationError, match="without surrounding whitespace"):
        DependencyHealth.model_validate(_dependency_payload(dependency=" canonical_event_bus "))


def test_dependency_health_rejects_blank_message() -> None:
    with pytest.raises(ValidationError, match="without surrounding whitespace"):
        DependencyHealth.model_validate(_dependency_payload(message=" "))


def test_service_health_rejects_blank_summary() -> None:
    with pytest.raises(ValidationError, match="without surrounding whitespace"):
        ServiceHealth.model_validate(_service_payload(summary=" Degraded "))


def test_adapter_health_rejects_blank_exchange() -> None:
    with pytest.raises(ValidationError, match="without surrounding whitespace"):
        AdapterHealth.model_validate(_adapter_payload(exchange=" kalshi "))


def test_adapter_health_rejects_negative_reconnect_attempts() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        AdapterHealth.model_validate(_adapter_payload(reconnect_attempts=-1))


def test_rate_limit_window_rejects_nonpositive_limit() -> None:
    with pytest.raises(ValidationError, match="greater than 0"):
        RateLimitWindow.model_validate(_rate_limit_window_payload(limit=0))


def test_rate_limit_window_rejects_remaining_above_limit() -> None:
    with pytest.raises(ValidationError, match="must not exceed limit"):
        RateLimitWindow.model_validate(_rate_limit_window_payload(limit=10, remaining=11))


def test_rate_limit_status_rejects_duplicate_window_names() -> None:
    with pytest.raises(ValidationError, match="unique names"):
        RateLimitStatus.model_validate(
            _rate_limit_status_payload(
                windows=(
                    _rate_limit_window_payload(name="orders"),
                    _rate_limit_window_payload(name="orders", remaining=41),
                )
            )
        )


def test_service_health_rejects_unknown_environment() -> None:
    with pytest.raises(ValidationError, match="Input should be"):
        ServiceHealth.model_validate(_service_payload(environment="sandbox"))


def test_service_health_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError, match="Input should be"):
        ServiceHealth.model_validate(_service_payload(status="offline"))


def test_service_health_rejects_unknown_trading_impact() -> None:
    with pytest.raises(ValidationError, match="String should match pattern"):
        ServiceHealth.model_validate(_service_payload(trading_impact="desk_only"))


def test_service_health_rejects_naive_since_datetime() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        ServiceHealth.model_validate(
            _service_payload(since=datetime.fromisoformat("2026-07-28T19:00:00"))
        )


def test_adapter_health_rejects_naive_last_message_datetime() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        AdapterHealth.model_validate(
            _adapter_payload(last_message_at=datetime.fromisoformat("2026-07-28T19:15:00"))
        )


def test_rate_limit_status_rejects_naive_measured_at_datetime() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        RateLimitStatus.model_validate(
            _rate_limit_status_payload(measured_at=datetime.fromisoformat("2026-07-28T19:15:00"))
        )


def test_service_health_rejects_duplicate_dependency_names() -> None:
    with pytest.raises(ValidationError, match="unique dependency names"):
        ServiceHealth.model_validate(
            _service_payload(
                dependencies=(
                    _dependency_payload(),
                    _dependency_payload(message="Still healthy."),
                )
            )
        )


def test_service_health_allows_health_readiness_and_liveness_to_vary_independently() -> None:
    health = ServiceHealth.model_validate(
        _service_payload(status=HealthStatus.HEALTHY, ready=False, alive=True)
    )

    assert health.status is HealthStatus.HEALTHY
    assert health.ready is False
    assert health.alive is True


def test_service_health_dependencies_are_immutable_after_validation() -> None:
    health = ServiceHealth.model_validate(_service_payload())
    dependency = DependencyHealth.model_validate(_dependency_payload(dependency="database"))
    original_hash = canonical_sha256(health)

    with pytest.raises(ValidationError, match="Instance is frozen"):
        health.dependencies += (dependency,)

    assert canonical_sha256(health) == original_hash


def test_adapter_health_is_immutable_after_validation() -> None:
    health = AdapterHealth.model_validate(_adapter_payload())
    original_hash = canonical_sha256(health)

    with pytest.raises(ValidationError, match="Instance is frozen"):
        health.connected = False

    assert canonical_sha256(health) == original_hash


def test_service_health_json_round_trip_normalizes_utc_and_stable_hash() -> None:
    health = ServiceHealth.model_validate(
        _service_payload(
            since="2026-07-28T13:00:00-06:00",
            last_success_at="2026-07-28T13:14:00-06:00",
            last_error_at="2026-07-28T13:10:00-06:00",
        )
    )
    canonical = canonical_json(health)

    assert '"since":"2026-07-28T19:00:00Z"' in canonical
    assert ServiceHealth.model_validate_json(canonical) == health
    assert canonical_sha256(health) == canonical_sha256(
        ServiceHealth.model_validate_json(canonical)
    )


def test_adapter_health_json_round_trip_normalizes_utc_and_stable_hash() -> None:
    health = AdapterHealth.model_validate(
        _adapter_payload(
            last_message_at="2026-07-28T13:15:00-06:00",
            last_heartbeat_at="2026-07-28T13:14:59-06:00",
            last_reconciliation_at="2026-07-28T13:00:00-06:00",
        )
    )
    canonical = canonical_json(health)

    assert '"last_message_at":"2026-07-28T19:15:00Z"' in canonical
    assert AdapterHealth.model_validate_json(canonical) == health
    assert canonical_sha256(health) == canonical_sha256(
        AdapterHealth.model_validate_json(canonical)
    )


def test_rate_limit_status_json_round_trip_normalizes_utc_and_stable_hash() -> None:
    status = RateLimitStatus.model_validate(
        _rate_limit_status_payload(
            measured_at="2026-07-28T13:15:00-06:00",
            windows=(_rate_limit_window_payload(resets_at="2026-07-28T13:16:00-06:00"),),
        )
    )
    canonical = canonical_json(status)

    assert '"measured_at":"2026-07-28T19:15:00Z"' in canonical
    assert '"resets_at":"2026-07-28T19:16:00Z"' in canonical
    assert RateLimitStatus.model_validate_json(canonical) == status
    assert canonical_sha256(status) == canonical_sha256(
        RateLimitStatus.model_validate_json(canonical)
    )


def test_service_health_json_schema_generation() -> None:
    json_schema = ServiceHealth.model_json_schema()

    assert json_schema["title"] == "ServiceHealth"
    assert "dependencies" in json_schema["properties"]


def test_adapter_health_json_schema_generation() -> None:
    json_schema = AdapterHealth.model_json_schema()

    assert json_schema["title"] == "AdapterHealth"
    assert "trading_gate_open" in json_schema["properties"]


def test_rate_limit_status_json_schema_generation() -> None:
    json_schema = RateLimitStatus.model_json_schema()

    assert json_schema["title"] == "RateLimitStatus"
    assert "windows" in json_schema["properties"]


def test_system_health_schema_registry_entries_exist() -> None:
    assert get_schema_model("dependency_health", 1) is DependencyHealth
    assert get_schema_model("service_health", 1) is ServiceHealth
    assert get_schema_model("adapter_health", 1) is AdapterHealth
    assert get_schema_model("rate_limit_window", 1) is RateLimitWindow
    assert get_schema_model("rate_limit_status", 1) is RateLimitStatus
    registration = get_schema_registration("service_health", 1)

    assert registration.model_path == "pmrp.schemas.system.ServiceHealth"
    assert (
        get_schema_registration("adapter_health", 1).model_path
        == "pmrp.schemas.system.AdapterHealth"
    )
