"""Property tests for simulation latency models."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.simulation import FixedLatencyModel

pytestmark = pytest.mark.property

_UTC_DATETIMES = st.datetimes(
    min_value=datetime.fromisoformat("2026-01-01T00:00:00"),
    max_value=datetime.fromisoformat("2026-12-31T23:59:59.999000"),
    timezones=st.just(UTC),
)
_LATENCY_MS = st.integers(min_value=0, max_value=86_400_000)


@given(accepted_at=_UTC_DATETIMES, latency_ms=_LATENCY_MS)
def test_fixed_latency_model_adds_exact_integer_milliseconds(
    accepted_at: datetime,
    latency_ms: int,
) -> None:
    model = FixedLatencyModel.from_milliseconds(latency_ms)

    activation_time = model.activation_time(accepted_at=accepted_at)

    assert activation_time == accepted_at + timedelta(milliseconds=latency_ms)
    assert activation_time.tzinfo is UTC


@given(accepted_at=_UTC_DATETIMES, latency_ms=_LATENCY_MS)
def test_fixed_latency_model_is_deterministic(
    accepted_at: datetime,
    latency_ms: int,
) -> None:
    model = FixedLatencyModel.from_milliseconds(latency_ms)

    assert model.activation_time(accepted_at=accepted_at) == model.activation_time(
        accepted_at=accepted_at
    )
