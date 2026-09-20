"""Simulation result summary tests."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from pmrp.schemas.serialization import canonical_sha256
from pmrp.schemas.simulation import SimulationConfiguration
from pmrp.simulation import (
    SIMULATION_RESULT_CHECKSUM_VERSION,
    SimulationArtifact,
    SimulationConfigurationError,
    SimulationMetric,
    SimulationResult,
    SimulationSourceType,
    calculate_simulation_result_checksum,
)

pytestmark = pytest.mark.unit


def test_simulation_result_builds_deterministic_summary() -> None:
    configuration = _configuration()
    artifacts = (
        SimulationArtifact(
            sequence=1,
            artifact_type="fill",
            artifact_id="fill_001",
            artifact_hash=_artifact_hash("fill-001"),
            source_type=SimulationSourceType.SIMULATED_OUTPUT,
        ),
        SimulationArtifact(
            sequence=0,
            artifact_type="order_intent",
            artifact_id="intent_001",
            artifact_hash=_artifact_hash("intent-001"),
            source_type=SimulationSourceType.OBSERVED_FACT,
        ),
    )
    metrics = (
        SimulationMetric(name="fill_rate", value=Decimal("0.50"), unit="ratio"),
        SimulationMetric(name="simulated_pnl", value=Decimal("12.34"), unit="USD"),
    )

    result = SimulationResult.build(
        configuration=configuration,
        artifacts=artifacts,
        metrics=metrics,
    )

    assert result.configuration == configuration
    assert result.configuration_hash == canonical_sha256(configuration)
    assert result.artifacts[0].sequence == 0
    assert result.metrics[0].name == "fill_rate"
    assert result.result_checksum == calculate_simulation_result_checksum(
        configuration=configuration,
        artifacts=result.artifacts,
        metrics=result.metrics,
    )
    assert result.canonical_payload()["checksum_version"] == SIMULATION_RESULT_CHECKSUM_VERSION
    assert result.canonical_payload()["result_checksum"] == result.result_checksum
    assert result.source_type_counts[SimulationSourceType.OBSERVED_FACT] == 1
    assert result.source_type_counts[SimulationSourceType.SIMULATED_OUTPUT] == 1


def test_simulation_result_checksum_is_independent_of_metric_and_artifact_input_order() -> None:
    configuration = _configuration()
    first_artifact = SimulationArtifact(
        sequence=0,
        artifact_type="order",
        artifact_id="ord_001",
        artifact_hash=_artifact_hash("order-001"),
        source_type=SimulationSourceType.SIMULATED_OUTPUT,
    )
    second_artifact = SimulationArtifact(
        sequence=1,
        artifact_type="fill",
        artifact_id="fill_001",
        artifact_hash=_artifact_hash("fill-001"),
        source_type=SimulationSourceType.SIMULATED_OUTPUT,
    )
    first_metric = SimulationMetric(name="filled_quantity", value=Decimal("3"), unit="contracts")
    second_metric = SimulationMetric(name="fees", value=Decimal("0.01"), unit="USD")

    first = SimulationResult.build(
        configuration=configuration,
        artifacts=(first_artifact, second_artifact),
        metrics=(first_metric, second_metric),
    )
    second = SimulationResult.build(
        configuration=configuration,
        artifacts=(second_artifact, first_artifact),
        metrics=(second_metric, first_metric),
    )

    assert first.artifacts == second.artifacts
    assert first.metrics == second.metrics
    assert first.result_checksum == second.result_checksum


def test_simulation_result_checksum_changes_when_inputs_change() -> None:
    configuration = _configuration()
    base_metric = SimulationMetric(name="fill_rate", value=Decimal("0.50"), unit="ratio")
    changed_metric = SimulationMetric(name="fill_rate", value=Decimal("0.51"), unit="ratio")

    base_checksum = calculate_simulation_result_checksum(
        configuration=configuration,
        metrics=(base_metric,),
    )
    changed_checksum = calculate_simulation_result_checksum(
        configuration=configuration,
        metrics=(changed_metric,),
    )

    assert base_checksum != changed_checksum


def test_simulation_result_constructor_enforces_invariants() -> None:
    configuration = _configuration()
    first_artifact = SimulationArtifact(
        sequence=0,
        artifact_type="order",
        artifact_id="ord_001",
        artifact_hash=_artifact_hash("order-001"),
        source_type=SimulationSourceType.SIMULATED_OUTPUT,
    )
    second_artifact = SimulationArtifact(
        sequence=1,
        artifact_type="fill",
        artifact_id="fill_001",
        artifact_hash=_artifact_hash("fill-001"),
        source_type=SimulationSourceType.SIMULATED_OUTPUT,
    )
    metric = SimulationMetric(name="filled_quantity", value=Decimal("3"), unit="contracts")
    result_checksum = calculate_simulation_result_checksum(
        configuration=configuration,
        artifacts=(second_artifact, first_artifact),
        metrics=(metric,),
    )

    result = SimulationResult(
        configuration=configuration,
        artifacts=(second_artifact, first_artifact),
        metrics=(metric,),
        result_checksum=result_checksum,
    )

    assert result.artifacts == (first_artifact, second_artifact)
    assert result.result_checksum == result_checksum

    with pytest.raises(SimulationConfigurationError) as checksum_error:
        SimulationResult(
            configuration=configuration,
            artifacts=(first_artifact, second_artifact),
            metrics=(metric,),
            result_checksum=_artifact_hash("stale-result"),
        )

    assert checksum_error.value.reason_code == "simulation_result_checksum_mismatch"

    with pytest.raises(SimulationConfigurationError) as duplicate_error:
        SimulationResult(
            configuration=configuration,
            artifacts=(first_artifact, first_artifact),
            metrics=(),
            result_checksum=_artifact_hash("unused-result"),
        )

    assert duplicate_error.value.reason_code == "simulation_result_artifact_sequence_duplicate"


def test_simulation_results_reject_invalid_inputs() -> None:
    configuration = _configuration()

    with pytest.raises(SimulationConfigurationError) as configuration_error:
        SimulationResult.build(configuration="not-config")  # type: ignore[arg-type]

    assert configuration_error.value.reason_code == "simulation_result_configuration_invalid"

    with pytest.raises(TypeError, match="artifacts"):
        SimulationResult.build(configuration=configuration, artifacts=[])  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="metrics"):
        SimulationResult.build(configuration=configuration, metrics=[])  # type: ignore[arg-type]

    with pytest.raises(SimulationConfigurationError) as artifact_error:
        SimulationResult.build(
            configuration=configuration,
            artifacts=(
                SimulationArtifact(
                    sequence=0,
                    artifact_type="order",
                    artifact_id="ord_001",
                    artifact_hash=_artifact_hash("order-001"),
                    source_type=SimulationSourceType.SIMULATED_OUTPUT,
                ),
                SimulationArtifact(
                    sequence=0,
                    artifact_type="fill",
                    artifact_id="fill_001",
                    artifact_hash=_artifact_hash("fill-001"),
                    source_type=SimulationSourceType.SIMULATED_OUTPUT,
                ),
            ),
        )

    assert artifact_error.value.reason_code == "simulation_result_artifact_sequence_duplicate"

    with pytest.raises(SimulationConfigurationError) as metric_error:
        SimulationResult.build(
            configuration=configuration,
            metrics=(
                SimulationMetric(name="fees", value=Decimal("0.01"), unit="USD"),
                SimulationMetric(name="fees", value=Decimal("0.02"), unit="USD"),
            ),
        )

    assert metric_error.value.reason_code == "simulation_result_metric_duplicate"


def test_simulation_artifacts_and_metrics_reject_invalid_values() -> None:
    with pytest.raises(ValueError, match="nonnegative"):
        SimulationArtifact(
            sequence=-1,
            artifact_type="fill",
            artifact_id="fill_001",
            artifact_hash=_artifact_hash("fill-001"),
            source_type=SimulationSourceType.SIMULATED_OUTPUT,
        )

    with pytest.raises(ValueError, match="canonical sha256 digest"):
        SimulationArtifact(
            sequence=0,
            artifact_type="fill",
            artifact_id="fill_001",
            artifact_hash="not-a-hash",
            source_type=SimulationSourceType.SIMULATED_OUTPUT,
        )

    with pytest.raises(ValueError, match="canonical sha256 digest"):
        SimulationArtifact(
            sequence=0,
            artifact_type="fill",
            artifact_id="fill_001",
            artifact_hash="sha256:raw_payload_must_not_fit_digest_shape",
            source_type=SimulationSourceType.SIMULATED_OUTPUT,
        )

    with pytest.raises(TypeError, match="SimulationSourceType"):
        SimulationArtifact(
            sequence=0,
            artifact_type="fill",
            artifact_id="fill_001",
            artifact_hash=_artifact_hash("fill-001"),
            source_type="simulated_output",  # type: ignore[arg-type]
        )

    with pytest.raises(TypeError, match="float input"):
        SimulationMetric(name="fill_rate", value=0.5, unit="ratio")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="nonempty"):
        SimulationMetric(name=" fill_rate", value=Decimal("0.5"), unit="ratio")


def test_simulation_results_do_not_use_wall_clock_random_network_storage_or_live_boundaries() -> (
    None
):
    source = Path(__file__).resolve().parents[3] / "src" / "pmrp" / "simulation" / "results.py"
    text = source.read_text(encoding="utf-8")

    assert "datetime.now" not in text
    assert "time.time" not in text
    assert "random." not in text
    assert "pmrp.adapters" not in text
    assert "pmrp.execution" not in text
    assert "pmrp.risk" not in text
    assert "sqlalchemy" not in text
    assert "asyncpg" not in text
    assert "httpx" not in text
    assert "requests" not in text


def _configuration(**overrides: object) -> SimulationConfiguration:
    payload: dict[str, object] = {
        "simulation_version": "sim-v1",
        "fill_model": "touch_fill_v1",
        "queue_model": "immediate_touch_v1",
        "latency_model": "fixed_latency_v1",
        "fee_model": "fee_table_v1",
        "rejection_model": "bounded_rejection_v1",
        "slippage_model": "bps_slippage_v1",
        "settlement_model": "binary_settlement_v1",
        "random_seed": 42,
        "fixed_latency_ms": 125,
        "taker_slippage_bps": "1.50",
        "parameters": {},
    }
    payload.update(overrides)
    return SimulationConfiguration.model_validate(payload)


def _artifact_hash(value: str) -> str:
    return canonical_sha256({"artifact": value})
