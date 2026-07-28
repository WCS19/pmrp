import json
from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from pmrp.schemas.serialization import canonical_json, canonical_sha256
from pmrp.schemas.strategy import Signal, SignalDirection
from pmrp.schemas.versions import get_schema_model, get_schema_registration

pytestmark = pytest.mark.unit


def _signal_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "signal_id": "sig_01j00000000000000000000000",
        "strategy_id": "strat_fed_value_v1",
        "market_id": "mkt_01j00000000000000000000000",
        "contract_id": "ctr_01j00000000000000000000000",
        "outcome_id": "out_yes",
        "signal_type": "fair_value_gap",
        "direction": SignalDirection.BUY,
        "strength": "0.65",
        "fair_probability": "0.47",
        "confidence": "0.72",
        "valid_from": "2026-07-27T15:00:00.140000Z",
        "valid_until": "2026-07-27T15:00:02.140000Z",
        "model_id": "mdl_fed_probability",
        "model_version": "1.4.2",
        "feature_snapshot_id": "feat_01j00000000000000000000000",
        "reason_code": "MODEL_ABOVE_ASK",
        "reason_text": "Fair probability exceeds executable ask after cost.",
        "correlation_id": "corr_01j00000000000000000000000",
    }
    payload.update(overrides)
    return payload


def test_signal_accepts_valid_full_payload_and_exact_decimals() -> None:
    signal = Signal.model_validate(_signal_payload())

    assert signal.direction is SignalDirection.BUY
    assert signal.strength == Decimal("0.65")
    assert signal.fair_probability == Decimal("0.47")
    assert signal.confidence == Decimal("0.72")


def test_signal_accepts_minimum_payload() -> None:
    signal = Signal.model_validate(
        _signal_payload(
            contract_id=None,
            outcome_id=None,
            strength=None,
            fair_probability=None,
            confidence=None,
            valid_until=None,
            model_id=None,
            model_version=None,
            feature_snapshot_id=None,
            reason_text=None,
        )
    )

    assert signal.contract_id is None
    assert signal.reason_text is None


def test_signal_accepts_all_documented_directions() -> None:
    for direction in SignalDirection:
        signal = Signal.model_validate(_signal_payload(direction=direction))

        assert signal.direction is direction


def test_signal_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Signal.model_validate(_signal_payload(unexpected=True))


def test_signal_rejects_invalid_signal_identifier() -> None:
    with pytest.raises(ValidationError, match="SignalId must start"):
        Signal.model_validate(_signal_payload(signal_id="signal_001"))


def test_signal_rejects_invalid_strategy_identifier() -> None:
    with pytest.raises(ValidationError, match="StrategyId must start"):
        Signal.model_validate(_signal_payload(strategy_id="strategy_fed_value_v1"))


def test_signal_rejects_invalid_direction_enum() -> None:
    with pytest.raises(ValidationError):
        Signal.model_validate(_signal_payload(direction="hold"))


def test_signal_rejects_float_probability() -> None:
    with pytest.raises(TypeError, match="float input"):
        Signal.model_validate(_signal_payload(fair_probability=0.47))


def test_signal_rejects_fair_probability_above_one() -> None:
    with pytest.raises(ValidationError, match="less than or equal to 1"):
        Signal.model_validate(_signal_payload(fair_probability="1.01"))


def test_signal_rejects_negative_confidence() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        Signal.model_validate(_signal_payload(confidence="-0.01"))


def test_signal_rejects_naive_valid_from() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        Signal.model_validate(
            _signal_payload(valid_from=datetime.fromisoformat("2026-07-27T15:00:00.140000"))
        )


def test_signal_rejects_invalid_validity_window() -> None:
    with pytest.raises(ValidationError, match="valid_until must be after"):
        Signal.model_validate(_signal_payload(valid_until="2026-07-27T15:00:00.140000Z"))


def test_signal_rejects_missing_reason_code() -> None:
    payload = _signal_payload()
    del payload["reason_code"]

    with pytest.raises(ValidationError, match="Field required"):
        Signal.model_validate(payload)


def test_signal_rejects_invalid_model_lineage() -> None:
    with pytest.raises(ValidationError, match="ModelId must start"):
        Signal.model_validate(_signal_payload(model_id="model_fed_probability"))


def test_signal_rejects_invalid_feature_lineage() -> None:
    with pytest.raises(ValidationError, match="FeatureSnapshotId must start"):
        Signal.model_validate(_signal_payload(feature_snapshot_id="feature_001"))


def test_signal_rejects_invalid_correlation_id() -> None:
    with pytest.raises(ValidationError, match="CorrelationId must start"):
        Signal.model_validate(_signal_payload(correlation_id="corr-001"))


def test_signal_json_round_trip_and_stable_hash() -> None:
    signal = Signal.model_validate_json(json.dumps({**_signal_payload(), "direction": "buy"}))
    canonical = canonical_json(signal)

    assert Signal.model_validate_json(canonical) == signal
    assert canonical_sha256(signal) == canonical_sha256(Signal.model_validate_json(canonical))


def test_signal_json_schema_generation() -> None:
    json_schema = Signal.model_json_schema()

    assert json_schema["title"] == "Signal"
    assert "fair_probability" in json_schema["properties"]


def test_signal_registry_entry_exists() -> None:
    assert get_schema_model("signal", 1) is Signal
    assert get_schema_registration("signal", 1).model_path == "pmrp.schemas.strategy.Signal"
