import json
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.schemas.serialization import canonical_json, canonical_sha256
from pmrp.schemas.strategy import Signal, SignalDirection

pytestmark = pytest.mark.property

_UNIT_DECIMALS = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("1"),
    allow_nan=False,
    allow_infinity=False,
    places=6,
)


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


@given(fair_probability=_UNIT_DECIMALS, confidence=_UNIT_DECIMALS)
def test_signal_accepts_generated_probability_bounds(
    fair_probability: Decimal,
    confidence: Decimal,
) -> None:
    signal = Signal.model_validate(
        _signal_payload(
            fair_probability=str(fair_probability),
            confidence=str(confidence),
        )
    )

    assert Decimal("0") <= signal.fair_probability <= Decimal("1")
    assert Decimal("0") <= signal.confidence <= Decimal("1")


@given(value=_UNIT_DECIMALS)
def test_signal_decimal_json_round_trips_exactly(value: Decimal) -> None:
    signal = Signal.model_validate_json(
        json.dumps(
            _signal_payload(
                direction="buy",
                fair_probability=str(value),
                confidence=str(value),
            )
        )
    )

    assert Signal.model_validate_json(canonical_json(signal)) == signal


@given(direction=st.sampled_from(tuple(SignalDirection)))
def test_signal_hash_is_stable_across_repeated_serialization(
    direction: SignalDirection,
) -> None:
    signal = Signal.model_validate(_signal_payload(direction=direction))

    assert canonical_sha256(signal) == canonical_sha256(
        Signal.model_validate_json(canonical_json(signal))
    )
