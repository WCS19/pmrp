"""Deterministic simulation result summaries and checksums."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType

from pmrp.schemas.numeric import parse_decimal
from pmrp.schemas.serialization import canonical_sha256
from pmrp.schemas.simulation import SimulationConfiguration
from pmrp.simulation.errors import SimulationConfigurationError

SIMULATION_RESULT_CHECKSUM_VERSION = "simulation_result_checksum_v1"

_MAX_TEXT_LENGTH = 128
_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class SimulationSourceType(StrEnum):
    """Classify the provenance of a simulation result input or output."""

    INFERRED_BEHAVIOR = "inferred_behavior"
    OBSERVED_FACT = "observed_fact"
    SIMULATED_OUTPUT = "simulated_output"
    STOCHASTIC_ASSUMPTION = "stochastic_assumption"


@dataclass(frozen=True, slots=True)
class SimulationArtifact:
    """One hashed simulation output or input artifact included in a result."""

    sequence: int
    artifact_type: str
    artifact_id: str
    artifact_hash: str
    source_type: SimulationSourceType

    def __post_init__(self) -> None:
        if type(self.sequence) is not int:
            msg = "artifact sequence must be an integer"
            raise TypeError(msg)
        if self.sequence < 0:
            msg = "artifact sequence must be nonnegative"
            raise ValueError(msg)
        object.__setattr__(
            self,
            "artifact_type",
            _validate_text(self.artifact_type, field_name="artifact_type"),
        )
        object.__setattr__(
            self,
            "artifact_id",
            _validate_text(self.artifact_id, field_name="artifact_id"),
        )
        object.__setattr__(
            self,
            "artifact_hash",
            _validate_hash(self.artifact_hash, field_name="artifact_hash"),
        )
        if not isinstance(self.source_type, SimulationSourceType):
            msg = "source_type must be a SimulationSourceType"
            raise TypeError(msg)

    def canonical_payload(self) -> Mapping[str, object]:
        """Return stable JSON-compatible artifact data."""

        return {
            "artifact_hash": self.artifact_hash,
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "sequence": self.sequence,
            "source_type": self.source_type,
        }


@dataclass(frozen=True, slots=True)
class SimulationMetric:
    """One exact Decimal metric produced by a simulation run."""

    name: str
    value: Decimal
    unit: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _validate_text(self.name, field_name="metric name"))
        object.__setattr__(
            self,
            "value",
            parse_decimal(self.value, field_name="simulation metric value"),
        )
        object.__setattr__(self, "unit", _validate_text(self.unit, field_name="metric unit"))

    def canonical_payload(self) -> Mapping[str, object]:
        """Return stable JSON-compatible metric data."""

        return {"name": self.name, "unit": self.unit, "value": self.value}


@dataclass(frozen=True, slots=True)
class SimulationResult:
    """Deterministic result summary for one simulated run."""

    configuration: SimulationConfiguration
    artifacts: tuple[SimulationArtifact, ...]
    metrics: tuple[SimulationMetric, ...]
    result_checksum: str

    def __post_init__(self) -> None:
        configuration = _validate_configuration(self.configuration)
        artifacts = _normalize_artifacts(self.artifacts)
        metrics = _normalize_metrics(self.metrics)
        result_checksum = _validate_hash(self.result_checksum, field_name="result_checksum")
        expected_checksum = calculate_simulation_result_checksum(
            configuration=configuration,
            artifacts=artifacts,
            metrics=metrics,
        )
        if result_checksum != expected_checksum:
            raise SimulationConfigurationError(
                "Simulation result checksum must match canonical result payload",
                reason_code="simulation_result_checksum_mismatch",
                context={
                    "expected_checksum": expected_checksum,
                    "actual_checksum": result_checksum,
                },
            )
        object.__setattr__(self, "configuration", configuration)
        object.__setattr__(self, "artifacts", artifacts)
        object.__setattr__(self, "metrics", metrics)
        object.__setattr__(self, "result_checksum", result_checksum)

    @classmethod
    def build(
        cls,
        *,
        configuration: SimulationConfiguration,
        artifacts: tuple[SimulationArtifact, ...] = (),
        metrics: tuple[SimulationMetric, ...] = (),
    ) -> SimulationResult:
        """Build a simulation result with a deterministic checksum."""

        configuration = _validate_configuration(configuration)
        artifacts = _normalize_artifacts(artifacts)
        metrics = _normalize_metrics(metrics)
        result_checksum = calculate_simulation_result_checksum(
            configuration=configuration,
            artifacts=artifacts,
            metrics=metrics,
        )
        return cls(
            configuration=configuration,
            artifacts=artifacts,
            metrics=metrics,
            result_checksum=result_checksum,
        )

    @property
    def configuration_hash(self) -> str:
        """Return the stable hash of the simulation configuration."""

        return canonical_sha256(self.configuration)

    @property
    def source_type_counts(self) -> Mapping[SimulationSourceType, int]:
        """Return immutable artifact counts by source classification."""

        counts = Counter(artifact.source_type for artifact in self.artifacts)
        return MappingProxyType(dict(counts))

    def canonical_payload(self) -> Mapping[str, object]:
        """Return stable JSON-compatible result data including its checksum."""

        return _result_payload(
            configuration=self.configuration,
            artifacts=self.artifacts,
            metrics=self.metrics,
            result_checksum=self.result_checksum,
        )


def calculate_simulation_result_checksum(
    *,
    configuration: SimulationConfiguration,
    artifacts: tuple[SimulationArtifact, ...] = (),
    metrics: tuple[SimulationMetric, ...] = (),
) -> str:
    """Return the deterministic checksum for a simulation result summary."""

    configuration = _validate_configuration(configuration)
    artifacts = _normalize_artifacts(artifacts)
    metrics = _normalize_metrics(metrics)
    return canonical_sha256(
        _result_payload(
            configuration=configuration,
            artifacts=artifacts,
            metrics=metrics,
            result_checksum=None,
        )
    )


def _result_payload(
    *,
    configuration: SimulationConfiguration,
    artifacts: tuple[SimulationArtifact, ...],
    metrics: tuple[SimulationMetric, ...],
    result_checksum: str | None,
) -> Mapping[str, object]:
    payload: dict[str, object] = {
        "artifacts": [artifact.canonical_payload() for artifact in artifacts],
        "checksum_version": SIMULATION_RESULT_CHECKSUM_VERSION,
        "configuration_hash": canonical_sha256(configuration),
        "fee_model": configuration.fee_model,
        "fill_model": configuration.fill_model,
        "latency_model": configuration.latency_model,
        "metrics": [metric.canonical_payload() for metric in metrics],
        "queue_model": configuration.queue_model,
        "random_seed": configuration.random_seed,
        "rejection_model": configuration.rejection_model,
        "settlement_model": configuration.settlement_model,
        "simulation_version": configuration.simulation_version,
        "slippage_model": configuration.slippage_model,
    }
    if result_checksum is not None:
        payload["result_checksum"] = _validate_hash(
            result_checksum,
            field_name="result_checksum",
        )
    return payload


def _validate_configuration(configuration: SimulationConfiguration) -> SimulationConfiguration:
    if not isinstance(configuration, SimulationConfiguration):
        raise SimulationConfigurationError(
            "Simulation result requires a canonical SimulationConfiguration",
            reason_code="simulation_result_configuration_invalid",
        )
    return configuration


def _normalize_artifacts(
    artifacts: tuple[SimulationArtifact, ...],
) -> tuple[SimulationArtifact, ...]:
    if not isinstance(artifacts, tuple):
        msg = "artifacts must be a tuple"
        raise TypeError(msg)
    if any(not isinstance(artifact, SimulationArtifact) for artifact in artifacts):
        msg = "artifacts must contain only SimulationArtifact values"
        raise TypeError(msg)

    sorted_artifacts = tuple(sorted(artifacts, key=lambda artifact: artifact.sequence))
    sequences = [artifact.sequence for artifact in sorted_artifacts]
    if len(set(sequences)) != len(sequences):
        raise SimulationConfigurationError(
            "Simulation result artifacts must have unique sequences",
            reason_code="simulation_result_artifact_sequence_duplicate",
        )
    return sorted_artifacts


def _normalize_metrics(metrics: tuple[SimulationMetric, ...]) -> tuple[SimulationMetric, ...]:
    if not isinstance(metrics, tuple):
        msg = "metrics must be a tuple"
        raise TypeError(msg)
    if any(not isinstance(metric, SimulationMetric) for metric in metrics):
        msg = "metrics must contain only SimulationMetric values"
        raise TypeError(msg)

    sorted_metrics = tuple(sorted(metrics, key=lambda metric: (metric.name, metric.unit)))
    keys = [(metric.name, metric.unit) for metric in sorted_metrics]
    if len(set(keys)) != len(keys):
        raise SimulationConfigurationError(
            "Simulation result metrics must be unique by name and unit",
            reason_code="simulation_result_metric_duplicate",
        )
    return sorted_metrics


def _validate_hash(value: str, *, field_name: str) -> str:
    value = _validate_text(value, field_name=field_name)
    if _SHA256_PATTERN.fullmatch(value) is None:
        msg = f"{field_name} must be a canonical sha256 digest"
        raise ValueError(msg)
    return value


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
