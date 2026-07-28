import json
from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from pmrp.schemas.replay import ReplayManifest, ReplayResult, ReplaySession, ReplayState
from pmrp.schemas.serialization import canonical_json, canonical_sha256
from pmrp.schemas.versions import get_schema_model, get_schema_registration

pytestmark = pytest.mark.unit


def _money(amount: str, currency: str = "USD") -> dict[str, str]:
    return {"amount": amount, "currency": currency}


def _position_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "position_id": "pos_01j00000000000000000000000",
        "exchange": "kalshi",
        "account_id": "acct_paper_001",
        "market_id": "mkt_01j00000000000000000000000",
        "contract_id": "ctr_01j00000000000000000000000",
        "outcome_id": "out_yes",
        "quantity": "12",
        "average_entry_price": "0.42",
        "realized_pnl": _money("3.25"),
        "unrealized_pnl": _money("1.10"),
        "fees_paid": _money("0.12"),
        "rebates_received": _money("0.03"),
        "opened_at": "2026-07-28T15:00:00Z",
        "last_updated_at": "2026-07-28T15:30:00Z",
        "aggregate_version": 4,
    }
    payload.update(overrides)
    return payload


def _cash_balance_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "balance_id": "balance_usd_001",
        "exchange": "kalshi",
        "account_id": "acct_paper_001",
        "currency": "USD",
        "available": "800.25",
        "reserved": "199.75",
        "total": "1000.00",
        "captured_at": "2026-07-28T15:30:00Z",
    }
    payload.update(overrides)
    return payload


def _portfolio_snapshot_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "portfolio_id": "portfolio_replay",
        "captured_at": "2026-07-28T16:00:00Z",
        "positions": (_position_payload(),),
        "balances": (_cash_balance_payload(),),
        "realized_pnl": (_money("3.25"),),
        "unrealized_pnl": (_money("1.10"),),
        "gross_exposure": (_money("12.00"),),
        "net_exposure": (_money("12.00"),),
        "reconciliation_status": "healthy",
    }
    payload.update(overrides)
    return payload


def _manifest_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "replay_session_id": "rpl_01j00000000000000000000000",
        "dataset_id": "dataset_basic_market",
        "dataset_checksum": "sha256:dataset",
        "starts_at": "2026-07-28T15:00:00Z",
        "ends_at": "2026-07-28T16:00:00Z",
        "speed": "1.00",
        "deterministic": True,
        "random_seed": 42,
        "event_ordering_policy_version": "occurred-sequence-received-v1",
        "strategy_versions": {"strat_threshold_v1": "1.0.0"},
        "model_versions": {"mdl_fair_value": "2026.07.28"},
        "configuration_hash": "sha256:configuration",
        "code_commit": "abcdef1234567890",
        "dependency_lock_hash": "sha256:uvlock",
        "created_at": "2026-07-28T14:55:00Z",
        "created_by": "research_operator",
    }
    payload.update(overrides)
    return payload


def _session_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "replay_session_id": "rpl_01j00000000000000000000000",
        "manifest": _manifest_payload(),
        "state": ReplayState.RUNNING,
        "current_time": "2026-07-28T15:30:00Z",
        "processed_events": 125,
        "rejected_events": 1,
        "started_at": "2026-07-28T14:56:00Z",
        "completed_at": None,
        "result_checksum": None,
        "failure_message": None,
    }
    payload.update(overrides)
    return payload


def _result_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "replay_session_id": "rpl_01j00000000000000000000000",
        "processed_events": 1000,
        "generated_signals": 10,
        "generated_intents": 4,
        "simulated_orders": 4,
        "simulated_fills": 3,
        "final_portfolio": _portfolio_snapshot_payload(),
        "metrics": {"max_drawdown": "0.02", "sharpe": "1.15"},
        "result_checksum": "sha256:result",
        "completed_at": "2026-07-28T16:00:30Z",
    }
    payload.update(overrides)
    return payload


def test_replay_manifest_accepts_valid_payload_and_exact_decimal() -> None:
    manifest = ReplayManifest.model_validate(_manifest_payload())

    assert manifest.replay_session_id == "rpl_01j00000000000000000000000"
    assert manifest.speed == Decimal("1.00")
    assert manifest.random_seed == 42


def test_replay_manifest_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ReplayManifest.model_validate(_manifest_payload(unexpected=True))


def test_replay_manifest_rejects_float_speed() -> None:
    with pytest.raises(TypeError, match="float input"):
        ReplayManifest.model_validate(_manifest_payload(speed=1.0))


def test_replay_manifest_rejects_nonpositive_speed() -> None:
    with pytest.raises(ValidationError, match="greater than 0"):
        ReplayManifest.model_validate(_manifest_payload(speed="0"))


def test_replay_manifest_rejects_negative_seed() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        ReplayManifest.model_validate(_manifest_payload(random_seed=-1))


def test_replay_manifest_rejects_invalid_window() -> None:
    with pytest.raises(ValidationError, match="ends_at must be after"):
        ReplayManifest.model_validate(_manifest_payload(ends_at="2026-07-28T15:00:00Z"))


def test_replay_manifest_rejects_naive_start_time() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        ReplayManifest.model_validate(
            _manifest_payload(starts_at=datetime.fromisoformat("2026-07-28T15:00:00"))
        )


def test_replay_manifest_rejects_empty_version_mapping_key() -> None:
    with pytest.raises(ValidationError, match="keys must be nonempty"):
        ReplayManifest.model_validate(_manifest_payload(strategy_versions={"": "1.0"}))


def test_replay_manifest_rejects_empty_version_mapping_value() -> None:
    with pytest.raises(ValidationError, match="values must be nonempty"):
        ReplayManifest.model_validate(_manifest_payload(model_versions={"mdl": ""}))


def test_replay_manifest_version_mappings_are_immutable_after_validation() -> None:
    manifest = ReplayManifest.model_validate(_manifest_payload())
    original_hash = canonical_sha256(manifest)

    with pytest.raises(TypeError, match="does not support item assignment"):
        manifest.strategy_versions["strat_other"] = "2.0.0"
    with pytest.raises(TypeError, match="does not support item assignment"):
        manifest.model_versions["mdl_other"] = "2026.07.29"

    assert canonical_sha256(manifest) == original_hash


def test_replay_session_accepts_running_payload() -> None:
    session = ReplaySession.model_validate(_session_payload())

    assert session.state is ReplayState.RUNNING
    assert session.processed_events == 125


def test_replay_session_accepts_completed_payload() -> None:
    session = ReplaySession.model_validate(
        _session_payload(
            state=ReplayState.COMPLETED,
            current_time="2026-07-28T16:00:00Z",
            completed_at="2026-07-28T16:00:30Z",
            result_checksum="sha256:result",
        )
    )

    assert session.state is ReplayState.COMPLETED
    assert session.result_checksum == "sha256:result"


def test_replay_session_accepts_failed_payload() -> None:
    session = ReplaySession.model_validate(
        _session_payload(
            state=ReplayState.FAILED,
            completed_at="2026-07-28T15:45:00Z",
            failure_message="Replay dataset checksum mismatch.",
        )
    )

    assert session.state is ReplayState.FAILED
    assert session.failure_message == "Replay dataset checksum mismatch."


def test_replay_session_rejects_current_time_before_manifest_window() -> None:
    with pytest.raises(ValidationError, match="within the manifest replay window"):
        ReplaySession.model_validate(_session_payload(current_time="2026-07-28T14:59:59Z"))


def test_replay_session_rejects_manifest_session_id_mismatch() -> None:
    with pytest.raises(ValidationError, match="must match manifest"):
        ReplaySession.model_validate(
            _session_payload(
                manifest=_manifest_payload(replay_session_id="rpl_01j11111111111111111111111")
            )
        )


def test_replay_session_rejects_active_without_started_at() -> None:
    with pytest.raises(ValidationError, match="requires started_at"):
        ReplaySession.model_validate(_session_payload(started_at=None))


def test_replay_session_rejects_active_without_current_time() -> None:
    with pytest.raises(ValidationError, match="requires current_time"):
        ReplaySession.model_validate(_session_payload(current_time=None))


def test_replay_session_rejects_active_with_terminal_fields() -> None:
    with pytest.raises(ValidationError, match="cannot contain terminal result fields"):
        ReplaySession.model_validate(
            _session_payload(completed_at="2026-07-28T15:45:00Z", result_checksum="sha256:result")
        )


def test_replay_session_rejects_terminal_without_completed_at() -> None:
    with pytest.raises(ValidationError, match="requires completed_at"):
        ReplaySession.model_validate(_session_payload(state=ReplayState.CANCELLED))


def test_replay_session_rejects_terminal_completed_before_manifest_created_at() -> None:
    with pytest.raises(
        ValidationError, match="completed_at must not be before manifest created_at"
    ):
        ReplaySession.model_validate(
            _session_payload(
                state=ReplayState.FAILED,
                started_at=None,
                completed_at="2026-07-28T14:54:00Z",
                failure_message="Replay failed before it was created.",
            )
        )


def test_replay_session_rejects_completed_without_checksum() -> None:
    with pytest.raises(ValidationError, match="requires result_checksum"):
        ReplaySession.model_validate(
            _session_payload(state=ReplayState.COMPLETED, completed_at="2026-07-28T16:00:30Z")
        )


def test_replay_session_rejects_failed_without_message() -> None:
    with pytest.raises(ValidationError, match="requires failure_message"):
        ReplaySession.model_validate(
            _session_payload(state=ReplayState.FAILED, completed_at="2026-07-28T15:45:00Z")
        )


def test_replay_session_rejects_non_failed_with_failure_message() -> None:
    with pytest.raises(ValidationError, match="non-failed replay session"):
        ReplaySession.model_validate(_session_payload(failure_message="Unexpected message."))


def test_replay_result_accepts_valid_payload() -> None:
    result = ReplayResult.model_validate(_result_payload())

    assert result.processed_events == 1000
    assert result.final_portfolio.portfolio_id == "portfolio_replay"


def test_replay_result_rejects_negative_counter() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        ReplayResult.model_validate(_result_payload(processed_events=-1))


def test_replay_result_rejects_empty_metric_key() -> None:
    with pytest.raises(ValidationError, match="keys must be nonempty"):
        ReplayResult.model_validate(_result_payload(metrics={"": "1.0"}))


def test_replay_result_metrics_are_immutable_after_validation() -> None:
    result = ReplayResult.model_validate(_result_payload())
    original_hash = canonical_sha256(result)

    with pytest.raises(TypeError, match="does not support item assignment"):
        result.metrics["new_metric"] = "1.0"

    assert canonical_sha256(result) == original_hash


def test_replay_result_json_round_trip_and_stable_hash() -> None:
    result = ReplayResult.model_validate_json(
        json.dumps(
            {
                **_result_payload(),
                "final_portfolio": {
                    **_portfolio_snapshot_payload(),
                    "positions": [_position_payload()],
                    "balances": [_cash_balance_payload()],
                    "realized_pnl": [_money("3.25")],
                    "unrealized_pnl": [_money("1.10")],
                    "gross_exposure": [_money("12.00")],
                    "net_exposure": [_money("12.00")],
                },
            }
        )
    )
    canonical = canonical_json(result)

    assert ReplayResult.model_validate_json(canonical) == result
    assert canonical_sha256(result) == canonical_sha256(ReplayResult.model_validate_json(canonical))


def test_replay_json_schema_generation() -> None:
    json_schema = ReplayManifest.model_json_schema()

    assert json_schema["title"] == "ReplayManifest"
    assert "dataset_checksum" in json_schema["properties"]


def test_replay_schema_registry_entries_exist() -> None:
    assert get_schema_model("replay_manifest", 1) is ReplayManifest
    assert get_schema_model("replay_session", 1) is ReplaySession
    assert get_schema_model("replay_result", 1) is ReplayResult
    registration = get_schema_registration("replay_manifest", 1)

    assert registration.model_path == "pmrp.schemas.replay.ReplayManifest"
