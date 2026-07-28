from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.schemas.replay import ReplayManifest, ReplayResult
from pmrp.schemas.serialization import canonical_json, canonical_sha256

pytestmark = pytest.mark.property

_POSITIVE_DECIMALS = st.decimals(
    min_value=Decimal("0.0001"),
    max_value=Decimal("1000000"),
    allow_nan=False,
    allow_infinity=False,
    places=4,
)

_NONNEGATIVE_COUNTS = st.integers(min_value=0, max_value=1_000_000)


def _money(amount: str, currency: str = "USD") -> dict[str, str]:
    return {"amount": amount, "currency": currency}


def _position_payload() -> dict[str, object]:
    return {
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


def _cash_balance_payload() -> dict[str, object]:
    return {
        "balance_id": "balance_usd_001",
        "exchange": "kalshi",
        "account_id": "acct_paper_001",
        "currency": "USD",
        "available": "800.25",
        "reserved": "199.75",
        "total": "1000.00",
        "captured_at": "2026-07-28T15:30:00Z",
    }


def _portfolio_snapshot_payload() -> dict[str, object]:
    return {
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


def _manifest_payload(*, speed: Decimal) -> dict[str, object]:
    return {
        "replay_session_id": "rpl_01j00000000000000000000000",
        "dataset_id": "dataset_basic_market",
        "dataset_checksum": "sha256:dataset",
        "starts_at": "2026-07-28T15:00:00Z",
        "ends_at": "2026-07-28T16:00:00Z",
        "speed": str(speed),
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


def _result_payload(
    *,
    processed_events: int,
    generated_signals: int,
    generated_intents: int,
) -> dict[str, object]:
    return {
        "replay_session_id": "rpl_01j00000000000000000000000",
        "processed_events": processed_events,
        "generated_signals": generated_signals,
        "generated_intents": generated_intents,
        "simulated_orders": generated_intents,
        "simulated_fills": generated_intents,
        "final_portfolio": _portfolio_snapshot_payload(),
        "metrics": {"max_drawdown": "0.02", "sharpe": "1.15"},
        "result_checksum": "sha256:result",
        "completed_at": "2026-07-28T16:00:30Z",
    }


@given(speed=_POSITIVE_DECIMALS)
def test_replay_manifest_accepts_generated_positive_speed(speed: Decimal) -> None:
    manifest = ReplayManifest.model_validate(_manifest_payload(speed=speed))

    assert manifest.speed == speed
    assert canonical_sha256(manifest) == canonical_sha256(
        ReplayManifest.model_validate_json(canonical_json(manifest))
    )


@given(
    processed_events=_NONNEGATIVE_COUNTS,
    generated_signals=_NONNEGATIVE_COUNTS,
    generated_intents=_NONNEGATIVE_COUNTS,
)
def test_replay_result_accepts_generated_nonnegative_counts(
    processed_events: int,
    generated_signals: int,
    generated_intents: int,
) -> None:
    result = ReplayResult.model_validate(
        _result_payload(
            processed_events=processed_events,
            generated_signals=generated_signals,
            generated_intents=generated_intents,
        )
    )

    assert result.processed_events == processed_events
    assert result.generated_signals == generated_signals
    assert result.generated_intents == generated_intents
    assert canonical_sha256(result) == canonical_sha256(
        ReplayResult.model_validate_json(canonical_json(result))
    )
