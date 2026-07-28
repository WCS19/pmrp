from decimal import Decimal

import pytest
from pydantic import ValidationError

from pmrp.schemas.serialization import canonical_json, canonical_sha256
from pmrp.schemas.simulation import SimulationConfiguration
from pmrp.schemas.versions import get_schema_model, get_schema_registration

pytestmark = pytest.mark.unit


def _configuration_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "simulation_version": "sim-v1",
        "fill_model": "pro_rata_fill_v1",
        "queue_model": "fifo_queue_v1",
        "latency_model": "fixed_latency_v1",
        "fee_model": "kalshi_fee_v1",
        "rejection_model": "bounded_rejection_v1",
        "slippage_model": "bps_slippage_v1",
        "settlement_model": "binary_settlement_v1",
        "random_seed": 20260728,
        "fixed_latency_ms": 125,
        "maker_fill_probability": "0.25",
        "taker_slippage_bps": "1.50",
        "parameters": {
            "minimum_resting_ms": "250",
            "queue_depth_limit": "1000",
        },
    }
    payload.update(overrides)
    return payload


def test_simulation_configuration_accepts_valid_payload_and_exact_decimals() -> None:
    configuration = SimulationConfiguration.model_validate(_configuration_payload())

    assert configuration.simulation_version == "sim-v1"
    assert configuration.maker_fill_probability == Decimal("0.25")
    assert configuration.taker_slippage_bps == Decimal("1.50")
    assert configuration.fixed_latency_ms == 125


def test_simulation_configuration_defaults_parameters_to_immutable_empty_mapping() -> None:
    configuration = SimulationConfiguration.model_validate(_configuration_payload(parameters={}))
    original_hash = canonical_sha256(configuration)

    with pytest.raises(TypeError, match="does not support item assignment"):
        configuration.parameters["late_parameter"] = "changed"

    assert canonical_sha256(configuration) == original_hash


def test_simulation_configuration_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SimulationConfiguration.model_validate(_configuration_payload(unexpected=True))


def test_simulation_configuration_rejects_float_probability() -> None:
    with pytest.raises(TypeError, match="float input"):
        SimulationConfiguration.model_validate(_configuration_payload(maker_fill_probability=0.25))


def test_simulation_configuration_rejects_float_slippage() -> None:
    with pytest.raises(TypeError, match="float input"):
        SimulationConfiguration.model_validate(_configuration_payload(taker_slippage_bps=1.5))


def test_simulation_configuration_rejects_probability_outside_unit_interval() -> None:
    with pytest.raises(ValidationError, match="less than or equal to 1"):
        SimulationConfiguration.model_validate(
            _configuration_payload(maker_fill_probability="1.0001")
        )


def test_simulation_configuration_rejects_negative_slippage() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        SimulationConfiguration.model_validate(_configuration_payload(taker_slippage_bps="-0.01"))


def test_simulation_configuration_rejects_negative_latency() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        SimulationConfiguration.model_validate(_configuration_payload(fixed_latency_ms=-1))


def test_simulation_configuration_rejects_negative_seed() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        SimulationConfiguration.model_validate(_configuration_payload(random_seed=-1))


def test_simulation_configuration_rejects_empty_model_name() -> None:
    with pytest.raises(ValidationError, match="at least 1 character"):
        SimulationConfiguration.model_validate(_configuration_payload(fill_model=""))


def test_simulation_configuration_rejects_empty_parameter_key() -> None:
    with pytest.raises(ValidationError, match="keys must be nonempty"):
        SimulationConfiguration.model_validate(_configuration_payload(parameters={"": "1"}))


def test_simulation_configuration_rejects_empty_parameter_value() -> None:
    with pytest.raises(ValidationError, match="values must be nonempty"):
        SimulationConfiguration.model_validate(_configuration_payload(parameters={"depth": ""}))


def test_simulation_configuration_parameters_are_immutable_after_validation() -> None:
    configuration = SimulationConfiguration.model_validate(_configuration_payload())
    original_hash = canonical_sha256(configuration)

    with pytest.raises(TypeError, match="does not support item assignment"):
        configuration.parameters["new_parameter"] = "1"

    assert canonical_sha256(configuration) == original_hash


def test_simulation_configuration_json_round_trip_and_stable_hash() -> None:
    configuration = SimulationConfiguration.model_validate(_configuration_payload())
    canonical = canonical_json(configuration)

    assert '"maker_fill_probability":"0.25"' in canonical
    assert '"taker_slippage_bps":"1.50"' in canonical
    assert SimulationConfiguration.model_validate_json(canonical) == configuration
    assert canonical_sha256(configuration) == canonical_sha256(
        SimulationConfiguration.model_validate_json(canonical)
    )


def test_simulation_configuration_hash_is_independent_of_parameter_order() -> None:
    first = SimulationConfiguration.model_validate(
        _configuration_payload(parameters={"a": "1", "b": "2"})
    )
    second = SimulationConfiguration.model_validate(
        _configuration_payload(parameters={"b": "2", "a": "1"})
    )

    assert canonical_sha256(first) == canonical_sha256(second)


def test_simulation_configuration_json_schema_generation() -> None:
    json_schema = SimulationConfiguration.model_json_schema()

    assert json_schema["title"] == "SimulationConfiguration"
    assert "maker_fill_probability" in json_schema["properties"]


def test_simulation_configuration_schema_registry_entry_exists() -> None:
    assert get_schema_model("simulation_configuration", 1) is SimulationConfiguration
    registration = get_schema_registration("simulation_configuration", 1)

    assert registration.model_path == "pmrp.schemas.simulation.SimulationConfiguration"
