"""Property tests for simulation result summaries."""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.schemas.simulation import SimulationConfiguration
from pmrp.simulation import (
    SimulationArtifact,
    SimulationMetric,
    SimulationResult,
    SimulationSourceType,
    calculate_simulation_result_checksum,
)

pytestmark = pytest.mark.property

_METRIC_VALUE = st.decimals(
    min_value=Decimal("-1000000"),
    max_value=Decimal("1000000"),
    allow_nan=False,
    allow_infinity=False,
    places=4,
)


@given(first_value=_METRIC_VALUE, second_value=_METRIC_VALUE)
def test_simulation_result_checksum_is_stable_across_metric_order(
    first_value: Decimal,
    second_value: Decimal,
) -> None:
    configuration = _configuration()
    first_metric = SimulationMetric(name="alpha", value=first_value, unit="USD")
    second_metric = SimulationMetric(name="beta", value=second_value, unit="USD")

    first = SimulationResult.build(
        configuration=configuration,
        metrics=(first_metric, second_metric),
    )
    second = SimulationResult.build(
        configuration=configuration,
        metrics=(second_metric, first_metric),
    )

    assert first.result_checksum == second.result_checksum


@given(value=_METRIC_VALUE)
def test_simulation_result_checksum_is_deterministic(value: Decimal) -> None:
    configuration = _configuration()
    metric = SimulationMetric(name="pnl", value=value, unit="USD")

    first = calculate_simulation_result_checksum(configuration=configuration, metrics=(metric,))
    second = calculate_simulation_result_checksum(configuration=configuration, metrics=(metric,))

    assert first == second


@given(value=_METRIC_VALUE)
def test_simulation_metric_preserves_exact_decimal(value: Decimal) -> None:
    metric = SimulationMetric(name="exact_metric", value=value, unit="ratio")

    assert metric.value == value
    assert metric.canonical_payload()["value"] == value


@given(value=_METRIC_VALUE)
def test_simulation_result_artifact_order_uses_explicit_sequence(value: Decimal) -> None:
    configuration = _configuration()
    metric = SimulationMetric(name="pnl", value=value, unit="USD")
    earlier_artifact = SimulationArtifact(
        sequence=0,
        artifact_type="order",
        artifact_id="ord_001",
        artifact_hash="sha256:order001",
        source_type=SimulationSourceType.SIMULATED_OUTPUT,
    )
    later_artifact = SimulationArtifact(
        sequence=1,
        artifact_type="fill",
        artifact_id="fill_001",
        artifact_hash="sha256:fill001",
        source_type=SimulationSourceType.SIMULATED_OUTPUT,
    )

    first = SimulationResult.build(
        configuration=configuration,
        artifacts=(earlier_artifact, later_artifact),
        metrics=(metric,),
    )
    second = SimulationResult.build(
        configuration=configuration,
        artifacts=(later_artifact, earlier_artifact),
        metrics=(metric,),
    )

    assert first.artifacts == second.artifacts
    assert first.result_checksum == second.result_checksum


def _configuration() -> SimulationConfiguration:
    return SimulationConfiguration.model_validate(
        {
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
    )
