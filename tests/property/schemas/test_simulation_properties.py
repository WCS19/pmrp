from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.schemas.serialization import canonical_json, canonical_sha256
from pmrp.schemas.simulation import SimulationConfiguration

pytestmark = pytest.mark.property

_PROBABILITIES = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("1"),
    allow_nan=False,
    allow_infinity=False,
    places=4,
)

_NONNEGATIVE_BPS = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("10000"),
    allow_nan=False,
    allow_infinity=False,
    places=4,
)

_NONNEGATIVE_INTS = st.integers(min_value=0, max_value=1_000_000)


def _configuration_payload(
    *,
    maker_fill_probability: Decimal,
    taker_slippage_bps: Decimal,
    random_seed: int,
    fixed_latency_ms: int,
) -> dict[str, object]:
    return {
        "simulation_version": "sim-v1",
        "fill_model": "pro_rata_fill_v1",
        "queue_model": "fifo_queue_v1",
        "latency_model": "fixed_latency_v1",
        "fee_model": "kalshi_fee_v1",
        "rejection_model": "bounded_rejection_v1",
        "slippage_model": "bps_slippage_v1",
        "settlement_model": "binary_settlement_v1",
        "random_seed": random_seed,
        "fixed_latency_ms": fixed_latency_ms,
        "maker_fill_probability": str(maker_fill_probability),
        "taker_slippage_bps": str(taker_slippage_bps),
        "parameters": {
            "minimum_resting_ms": str(fixed_latency_ms),
            "seed": str(random_seed),
        },
    }


@given(
    maker_fill_probability=_PROBABILITIES,
    taker_slippage_bps=_NONNEGATIVE_BPS,
    random_seed=_NONNEGATIVE_INTS,
    fixed_latency_ms=_NONNEGATIVE_INTS,
)
def test_simulation_configuration_accepts_generated_nonnegative_knobs(
    maker_fill_probability: Decimal,
    taker_slippage_bps: Decimal,
    random_seed: int,
    fixed_latency_ms: int,
) -> None:
    configuration = SimulationConfiguration.model_validate(
        _configuration_payload(
            maker_fill_probability=maker_fill_probability,
            taker_slippage_bps=taker_slippage_bps,
            random_seed=random_seed,
            fixed_latency_ms=fixed_latency_ms,
        )
    )

    assert configuration.maker_fill_probability == maker_fill_probability
    assert configuration.taker_slippage_bps == taker_slippage_bps
    assert configuration.random_seed == random_seed
    assert configuration.fixed_latency_ms == fixed_latency_ms
    assert canonical_sha256(configuration) == canonical_sha256(
        SimulationConfiguration.model_validate_json(canonical_json(configuration))
    )


@given(
    maker_fill_probability=_PROBABILITIES,
    taker_slippage_bps=_NONNEGATIVE_BPS,
)
def test_simulation_configuration_decimal_round_trip_is_exact(
    maker_fill_probability: Decimal,
    taker_slippage_bps: Decimal,
) -> None:
    configuration = SimulationConfiguration.model_validate(
        _configuration_payload(
            maker_fill_probability=maker_fill_probability,
            taker_slippage_bps=taker_slippage_bps,
            random_seed=42,
            fixed_latency_ms=250,
        )
    )

    reparsed = SimulationConfiguration.model_validate_json(canonical_json(configuration))

    assert reparsed.maker_fill_probability == maker_fill_probability
    assert reparsed.taker_slippage_bps == taker_slippage_bps
