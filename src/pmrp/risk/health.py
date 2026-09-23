"""Risk engine health reporting helpers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from pmrp.risk.engine import RiskEngine
from pmrp.risk.errors import RiskConfigurationError, RiskInputError
from pmrp.schemas.enums import Environment, HealthStatus
from pmrp.schemas.system import DependencyHealth, ServiceHealth
from pmrp.schemas.time import parse_utc_datetime

RISK_ENGINE_COMPONENT = "risk-engine"

_LABEL_MAX_LENGTH = 128
_HEALTHY_IMPACT = "none"
_BLOCKING_IMPACT = "global"


@dataclass(frozen=True, slots=True)
class RiskEngineHealthReporter:
    """Build canonical health reports for one configured risk engine."""

    service: str
    environment: Environment
    component: str = RISK_ENGINE_COMPONENT

    def __post_init__(self) -> None:
        _validate_label(self.service, field_name="service")
        _validate_label(self.component, field_name="component")
        if not isinstance(self.environment, Environment):
            raise RiskConfigurationError("environment must be a canonical Environment")

    def report(
        self,
        engine: RiskEngine,
        *,
        dependencies: Sequence[DependencyHealth] = (),
        checked_at: datetime,
        since: datetime | None = None,
        last_success_at: datetime | None = None,
        last_error_at: datetime | None = None,
    ) -> ServiceHealth:
        """Return a canonical service health snapshot for a configured risk engine."""

        if not isinstance(engine, RiskEngine):
            raise RiskInputError("risk health report requires a RiskEngine")
        dependencies = _freeze_dependencies(dependencies)
        checked_at = parse_utc_datetime(checked_at)
        since = checked_at if since is None else parse_utc_datetime(since)
        status = _status_for_dependencies(dependencies)
        last_success_at = (
            checked_at
            if last_success_at is None and status is HealthStatus.HEALTHY
            else _parse_optional_datetime(last_success_at)
        )
        last_error_at = _parse_optional_datetime(last_error_at)

        return ServiceHealth(
            service=self.service,
            component=self.component,
            environment=self.environment,
            status=status,
            since=since,
            summary=_summary(
                status=status, rule_count=len(engine.rules), dependencies=dependencies
            ),
            last_success_at=last_success_at,
            last_error_at=last_error_at,
            dependencies=dependencies,
            trading_impact=_HEALTHY_IMPACT if status is HealthStatus.HEALTHY else _BLOCKING_IMPACT,
            ready=status is HealthStatus.HEALTHY,
            alive=True,
        )


def build_risk_engine_health(
    engine: RiskEngine,
    *,
    service: str,
    environment: Environment,
    dependencies: Sequence[DependencyHealth] = (),
    checked_at: datetime,
    since: datetime | None = None,
    last_success_at: datetime | None = None,
    last_error_at: datetime | None = None,
) -> ServiceHealth:
    """Build a canonical risk engine health report using the default reporter."""

    return RiskEngineHealthReporter(service=service, environment=environment).report(
        engine,
        dependencies=dependencies,
        checked_at=checked_at,
        since=since,
        last_success_at=last_success_at,
        last_error_at=last_error_at,
    )


def _freeze_dependencies(
    dependencies: Sequence[DependencyHealth],
) -> tuple[DependencyHealth, ...]:
    if isinstance(dependencies, (str, bytes)) or not isinstance(dependencies, Sequence):
        msg = "risk health dependencies must be a sequence"
        raise TypeError(msg)
    frozen = tuple(dependencies)
    seen: set[str] = set()
    for dependency in frozen:
        if not isinstance(dependency, DependencyHealth):
            raise RiskInputError("risk health dependencies must be DependencyHealth records")
        if dependency.dependency in seen:
            raise RiskConfigurationError("risk health dependencies must be unique")
        seen.add(dependency.dependency)
    return frozen


def _status_for_dependencies(dependencies: tuple[DependencyHealth, ...]) -> HealthStatus:
    statuses = {dependency.status for dependency in dependencies}
    if HealthStatus.UNHEALTHY in statuses:
        return HealthStatus.UNHEALTHY
    if HealthStatus.UNKNOWN in statuses:
        return HealthStatus.UNKNOWN
    if HealthStatus.DEGRADED in statuses:
        return HealthStatus.DEGRADED
    return HealthStatus.HEALTHY


def _summary(
    *,
    status: HealthStatus,
    rule_count: int,
    dependencies: tuple[DependencyHealth, ...],
) -> str:
    rule_word = "rule" if rule_count == 1 else "rules"
    dependency_word = "dependency" if len(dependencies) == 1 else "dependencies"
    if status is HealthStatus.HEALTHY:
        return (
            f"Risk engine healthy with {rule_count} configured {rule_word} "
            f"and {len(dependencies)} healthy {dependency_word}."
        )
    if status is HealthStatus.UNHEALTHY:
        return "Risk engine blocked by an unhealthy dependency."
    if status is HealthStatus.UNKNOWN:
        return "Risk engine readiness unknown because a dependency is unknown."
    return "Risk engine degraded by a dependency."


def _parse_optional_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return parse_utc_datetime(value)


def _validate_label(value: str, *, field_name: str) -> str:
    if type(value) is not str:
        msg = f"risk health {field_name} must be a string"
        raise TypeError(msg)
    if value == "" or value.strip() != value:
        raise RiskConfigurationError(
            f"risk health {field_name} must be nonempty without surrounding whitespace"
        )
    if len(value) > _LABEL_MAX_LENGTH:
        raise RiskConfigurationError(f"risk health {field_name} must be at most 128 characters")
    return value
