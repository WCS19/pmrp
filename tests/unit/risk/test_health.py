"""Unit tests for risk engine health reporting."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pmrp.risk import (
    RISK_ENGINE_COMPONENT,
    RiskConfigurationError,
    RiskEngine,
    RiskEngineHealthReporter,
    RiskInputError,
    StrategyEnabledRule,
    build_risk_engine_health,
)
from pmrp.schemas.enums import Environment, HealthStatus
from pmrp.schemas.system import DependencyHealth

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


def test_risk_engine_health_reporter_builds_healthy_service_report() -> None:
    engine = _engine()
    dependencies = (
        _dependency("database", HealthStatus.HEALTHY),
        _dependency("event_bus", HealthStatus.HEALTHY),
    )

    health = RiskEngineHealthReporter(
        service="pmrp-risk",
        environment=Environment.TEST,
    ).report(engine, dependencies=dependencies, checked_at=NOW)

    assert health.service == "pmrp-risk"
    assert health.component == RISK_ENGINE_COMPONENT
    assert health.environment is Environment.TEST
    assert health.status is HealthStatus.HEALTHY
    assert health.summary == (
        "Risk engine healthy with 1 configured rule and 2 healthy dependencies."
    )
    assert health.dependencies == dependencies
    assert health.trading_impact == "none"
    assert health.ready is True
    assert health.alive is True
    assert health.since == NOW
    assert health.last_success_at == NOW
    assert health.last_error_at is None


def test_risk_engine_health_reporter_marks_degraded_dependency_not_ready() -> None:
    health = build_risk_engine_health(
        _engine(),
        service="pmrp-risk",
        environment=Environment.TEST,
        dependencies=(_dependency("database", HealthStatus.DEGRADED),),
        checked_at=NOW,
        since=NOW - timedelta(minutes=5),
        last_success_at=NOW - timedelta(minutes=10),
    )

    assert health.status is HealthStatus.DEGRADED
    assert health.summary == "Risk engine degraded by a dependency."
    assert health.trading_impact == "global"
    assert health.ready is False
    assert health.alive is True
    assert health.since == NOW - timedelta(minutes=5)
    assert health.last_success_at == NOW - timedelta(minutes=10)


def test_risk_engine_health_reporter_marks_unknown_dependency_not_ready() -> None:
    health = build_risk_engine_health(
        _engine(),
        service="pmrp-risk",
        environment=Environment.TEST,
        dependencies=(_dependency("event_bus", HealthStatus.UNKNOWN),),
        checked_at=NOW,
    )

    assert health.status is HealthStatus.UNKNOWN
    assert health.summary == "Risk engine readiness unknown because a dependency is unknown."
    assert health.trading_impact == "global"
    assert health.ready is False


def test_risk_engine_health_reporter_prioritizes_unhealthy_dependency() -> None:
    health = build_risk_engine_health(
        _engine(),
        service="pmrp-risk",
        environment=Environment.TEST,
        dependencies=(
            _dependency("event_bus", HealthStatus.UNKNOWN),
            _dependency("database", HealthStatus.UNHEALTHY),
        ),
        checked_at=NOW,
        last_error_at=NOW,
    )

    assert health.status is HealthStatus.UNHEALTHY
    assert health.summary == "Risk engine blocked by an unhealthy dependency."
    assert health.trading_impact == "global"
    assert health.ready is False
    assert health.last_success_at is None
    assert health.last_error_at == NOW


def test_risk_engine_health_reporter_validates_inputs() -> None:
    reporter = RiskEngineHealthReporter(service="pmrp-risk", environment=Environment.TEST)

    with pytest.raises(RiskConfigurationError, match="service"):
        RiskEngineHealthReporter(service=" pmrp-risk ", environment=Environment.TEST)
    with pytest.raises(RiskConfigurationError, match="Environment"):
        RiskEngineHealthReporter(  # type: ignore[arg-type]
            service="pmrp-risk",
            environment="test",
        )
    with pytest.raises(RiskInputError, match="RiskEngine"):
        reporter.report(object(), checked_at=NOW)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="dependencies"):
        reporter.report(_engine(), dependencies="database", checked_at=NOW)  # type: ignore[arg-type]
    with pytest.raises(RiskInputError, match="DependencyHealth"):
        reporter.report(_engine(), dependencies=(object(),), checked_at=NOW)  # type: ignore[arg-type]
    with pytest.raises(RiskConfigurationError, match="unique"):
        reporter.report(
            _engine(),
            dependencies=(
                _dependency("database", HealthStatus.HEALTHY),
                _dependency("database", HealthStatus.DEGRADED),
            ),
            checked_at=NOW,
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        reporter.report(_engine(), checked_at=NOW.replace(tzinfo=None))


def _engine() -> RiskEngine:
    return RiskEngine(rules=(StrategyEnabledRule(max_state_age=timedelta(seconds=5)),))


def _dependency(name: str, status: HealthStatus) -> DependencyHealth:
    return DependencyHealth(
        dependency=name,
        status=status,
        message=f"{name} {status.value}",
        checked_at=NOW,
    )
