from datetime import datetime

import pytest
from pydantic import ValidationError

from pmrp.schemas.enums import Environment, HealthStatus
from pmrp.schemas.serialization import canonical_json, canonical_sha256
from pmrp.schemas.system import DependencyHealth, ServiceHealth
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


def test_dependency_health_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        DependencyHealth.model_validate(_dependency_payload(unexpected=True))


def test_service_health_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ServiceHealth.model_validate(_service_payload(unexpected=True))


def test_dependency_health_rejects_blank_dependency_name() -> None:
    with pytest.raises(ValidationError, match="without surrounding whitespace"):
        DependencyHealth.model_validate(_dependency_payload(dependency=" canonical_event_bus "))


def test_dependency_health_rejects_blank_message() -> None:
    with pytest.raises(ValidationError, match="without surrounding whitespace"):
        DependencyHealth.model_validate(_dependency_payload(message=" "))


def test_service_health_rejects_blank_summary() -> None:
    with pytest.raises(ValidationError, match="without surrounding whitespace"):
        ServiceHealth.model_validate(_service_payload(summary=" Degraded "))


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


def test_service_health_rejects_ready_when_not_alive() -> None:
    with pytest.raises(ValidationError, match="must also be alive"):
        ServiceHealth.model_validate(_service_payload(ready=True, alive=False))


def test_service_health_rejects_healthy_when_not_ready() -> None:
    with pytest.raises(ValidationError, match="must be ready and alive"):
        ServiceHealth.model_validate(
            _service_payload(status=HealthStatus.HEALTHY, ready=False, alive=True)
        )


def test_service_health_dependencies_are_immutable_after_validation() -> None:
    health = ServiceHealth.model_validate(_service_payload())
    dependency = DependencyHealth.model_validate(_dependency_payload(dependency="database"))
    original_hash = canonical_sha256(health)

    with pytest.raises(ValidationError, match="Instance is frozen"):
        health.dependencies += (dependency,)

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


def test_service_health_json_schema_generation() -> None:
    json_schema = ServiceHealth.model_json_schema()

    assert json_schema["title"] == "ServiceHealth"
    assert "dependencies" in json_schema["properties"]


def test_system_health_schema_registry_entries_exist() -> None:
    assert get_schema_model("dependency_health", 1) is DependencyHealth
    assert get_schema_model("service_health", 1) is ServiceHealth
    registration = get_schema_registration("service_health", 1)

    assert registration.model_path == "pmrp.schemas.system.ServiceHealth"
