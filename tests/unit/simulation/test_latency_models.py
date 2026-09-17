"""Simulation latency model tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from pmrp.schemas.simulation import SimulationConfiguration
from pmrp.simulation import (
    FIXED_LATENCY_MODEL_NAME,
    FixedLatencyModel,
    LatencyModel,
    SimulationConfigurationError,
)

pytestmark = pytest.mark.unit

ACCEPTED_AT = datetime(2026, 8, 1, 15, 0, 0, 120_000, tzinfo=UTC)


def test_fixed_latency_model_returns_utc_activation_time() -> None:
    model = FixedLatencyModel.from_milliseconds(125)

    activation_time = model.activation_time(accepted_at=ACCEPTED_AT)

    assert isinstance(model, LatencyModel)
    assert model.latency == timedelta(milliseconds=125)
    assert activation_time == datetime(2026, 8, 1, 15, 0, 0, 245_000, tzinfo=UTC)


def test_fixed_latency_model_normalizes_accepted_at_to_utc() -> None:
    accepted_at = datetime(2026, 8, 1, 9, 0, 0, tzinfo=timezone(timedelta(hours=-6)))
    model = FixedLatencyModel.from_milliseconds(250)

    assert model.activation_time(accepted_at=accepted_at) == datetime(
        2026,
        8,
        1,
        15,
        0,
        0,
        250_000,
        tzinfo=UTC,
    )


def test_fixed_latency_model_accepts_zero_latency() -> None:
    model = FixedLatencyModel.from_milliseconds(0)

    assert model.activation_time(accepted_at=ACCEPTED_AT) == ACCEPTED_AT


def test_fixed_latency_model_rejects_invalid_latency_inputs() -> None:
    with pytest.raises(TypeError, match="int"):
        FixedLatencyModel.from_milliseconds(True)  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="int"):
        FixedLatencyModel.from_milliseconds(1.5)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="nonnegative"):
        FixedLatencyModel.from_milliseconds(-1)

    with pytest.raises(TypeError, match="timedelta"):
        FixedLatencyModel(latency=125)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="nonnegative"):
        FixedLatencyModel(latency=timedelta(milliseconds=-1))


def test_fixed_latency_model_rejects_invalid_activation_inputs() -> None:
    model = FixedLatencyModel.from_milliseconds(125)

    with pytest.raises(TypeError, match="datetime"):
        model.activation_time(accepted_at="2026-08-01T15:00:00Z")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="timezone-aware"):
        model.activation_time(accepted_at=datetime.fromisoformat("2026-08-01T15:00:00"))


def test_fixed_latency_model_loads_from_simulation_configuration() -> None:
    configuration = _configuration(fixed_latency_ms=125)

    model = FixedLatencyModel.from_configuration(configuration)

    assert model.latency == timedelta(milliseconds=125)


def test_fixed_latency_model_rejects_unsupported_configuration() -> None:
    with pytest.raises(SimulationConfigurationError) as unsupported_error:
        FixedLatencyModel.from_configuration(_configuration(latency_model="sampled_latency_v1"))

    assert unsupported_error.value.reason_code == "simulation_latency_model_unsupported"
    assert unsupported_error.value.context["latency_model"] == "sampled_latency_v1"

    with pytest.raises(SimulationConfigurationError) as missing_error:
        FixedLatencyModel.from_configuration(_configuration(fixed_latency_ms=None))

    assert missing_error.value.reason_code == "simulation_fixed_latency_missing"
    assert "fixed_latency_ms" not in repr(missing_error.value.context)


def _configuration(
    *,
    latency_model: str = FIXED_LATENCY_MODEL_NAME,
    fixed_latency_ms: int | None = 125,
) -> SimulationConfiguration:
    return SimulationConfiguration.model_validate(
        {
            "simulation_version": "sim-v1",
            "fill_model": "touch_fill_v1",
            "queue_model": "immediate_touch_v1",
            "latency_model": latency_model,
            "fee_model": "fixed_fee_v1",
            "rejection_model": "basic_rejection_v1",
            "slippage_model": "none_v1",
            "settlement_model": "none_v1",
            "random_seed": 42,
            "fixed_latency_ms": fixed_latency_ms,
            "parameters": {},
        }
    )
