import json
from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from pmrp.schemas.enums import OrderType, Side, TimeInForce
from pmrp.schemas.orders import ApprovedOrder, OrderIntent
from pmrp.schemas.serialization import canonical_json, canonical_sha256
from pmrp.schemas.versions import get_schema_model, get_schema_registration

pytestmark = pytest.mark.unit


def _intent_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "intent_id": "intent_01j00000000000000000000000",
        "strategy_id": "strat_threshold_v1",
        "market_id": "mkt_01j00000000000000000000000",
        "contract_id": "ctr_01j00000000000000000000000",
        "outcome_id": "out_yes",
        "side": Side.BUY,
        "quantity": "10",
        "limit_price": "0.43",
        "order_type": OrderType.LIMIT,
        "time_in_force": TimeInForce.GTC,
        "post_only": True,
        "reduce_only": False,
        "urgency": "0.75",
        "created_at": "2026-07-28T15:00:00Z",
        "expires_at": "2026-07-28T15:00:05Z",
        "signal_ids": ("sig_01j00000000000000000000000",),
        "correlation_id": "corr_01j00000000000000000000000",
        "idempotency_key": "idem-intent-001",
    }
    payload.update(overrides)
    return payload


def _approved_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "order_id": "ord_01j00000000000000000000000",
        "intent_id": "intent_01j00000000000000000000000",
        "strategy_id": "strat_threshold_v1",
        "risk_decision_id": "risk_01j00000000000000000000000",
        "exchange": "kalshi",
        "account_id": "acct_paper_001",
        "market_id": "mkt_01j00000000000000000000000",
        "contract_id": "ctr_01j00000000000000000000000",
        "outcome_id": "out_yes",
        "side": Side.BUY,
        "quantity": "10",
        "limit_price": "0.43",
        "order_type": OrderType.LIMIT,
        "time_in_force": TimeInForce.GTC,
        "post_only": True,
        "reduce_only": False,
        "approved_at": "2026-07-28T15:00:01Z",
        "approval_expires_at": "2026-07-28T15:00:03Z",
        "client_order_id": "client-order-001",
        "idempotency_key": "idem-order-001",
        "correlation_id": "corr_01j00000000000000000000000",
    }
    payload.update(overrides)
    return payload


def test_order_intent_accepts_valid_payload_and_exact_decimals() -> None:
    intent = OrderIntent.model_validate(_intent_payload())

    assert intent.quantity == Decimal("10")
    assert intent.limit_price == Decimal("0.43")
    assert intent.urgency == Decimal("0.75")
    assert intent.signal_ids == ("sig_01j00000000000000000000000",)


def test_order_intent_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        OrderIntent.model_validate(_intent_payload(unexpected=True))


def test_order_intent_rejects_missing_required_idempotency_key() -> None:
    payload = _intent_payload()
    del payload["idempotency_key"]

    with pytest.raises(ValidationError, match="Field required"):
        OrderIntent.model_validate(payload)


def test_order_intent_rejects_empty_idempotency_key() -> None:
    with pytest.raises(ValidationError, match="at least 1 character"):
        OrderIntent.model_validate(_intent_payload(idempotency_key=""))


def test_order_intent_rejects_invalid_strategy_identifier() -> None:
    with pytest.raises(ValidationError, match="StrategyId must start"):
        OrderIntent.model_validate(_intent_payload(strategy_id="strategy_threshold_v1"))


def test_order_intent_rejects_invalid_contract_identifier() -> None:
    with pytest.raises(ValidationError, match="ContractId must start"):
        OrderIntent.model_validate(_intent_payload(contract_id="contract_001"))


def test_order_intent_rejects_invalid_side_enum() -> None:
    with pytest.raises(ValidationError):
        OrderIntent.model_validate(_intent_payload(side="hold"))


def test_order_intent_rejects_float_quantity() -> None:
    with pytest.raises(TypeError, match="float input"):
        OrderIntent.model_validate(_intent_payload(quantity=1.0))


def test_order_intent_rejects_non_positive_quantity() -> None:
    with pytest.raises(ValidationError, match="greater than 0"):
        OrderIntent.model_validate(_intent_payload(quantity="0"))


def test_order_intent_limit_order_requires_limit_price() -> None:
    with pytest.raises(ValidationError, match="limit orders require limit_price"):
        OrderIntent.model_validate(_intent_payload(limit_price=None))


def test_order_intent_market_order_accepts_missing_limit_price() -> None:
    intent = OrderIntent.model_validate(
        _intent_payload(order_type=OrderType.MARKET, limit_price=None, post_only=False)
    )

    assert intent.order_type is OrderType.MARKET
    assert intent.limit_price is None


def test_order_intent_rejects_post_only_market_order() -> None:
    with pytest.raises(ValidationError, match="post_only is invalid"):
        OrderIntent.model_validate(_intent_payload(order_type=OrderType.MARKET, post_only=True))


def test_order_intent_rejects_expiry_before_creation() -> None:
    with pytest.raises(ValidationError, match="expires_at must be after"):
        OrderIntent.model_validate(_intent_payload(expires_at="2026-07-28T14:59:59Z"))


def test_order_intent_rejects_naive_creation_time() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        OrderIntent.model_validate(
            _intent_payload(created_at=datetime.fromisoformat("2026-07-28T15:00:00"))
        )


def test_order_intent_rejects_invalid_signal_lineage() -> None:
    with pytest.raises(ValidationError, match="SignalId must start"):
        OrderIntent.model_validate(_intent_payload(signal_ids=("signal_001",)))


def test_order_intent_rejects_urgency_outside_unit_interval() -> None:
    with pytest.raises(ValidationError, match="less than or equal to 1"):
        OrderIntent.model_validate(_intent_payload(urgency="1.01"))


def test_order_intent_json_round_trip_and_stable_hash() -> None:
    intent = OrderIntent.model_validate_json(
        json.dumps({**_intent_payload(), "signal_ids": ["sig_01j00000000000000000000000"]})
    )

    canonical = canonical_json(intent)

    assert OrderIntent.model_validate_json(canonical) == intent
    assert canonical_sha256(intent) == canonical_sha256(OrderIntent.model_validate_json(canonical))


def test_order_intent_json_schema_generation() -> None:
    json_schema = OrderIntent.model_json_schema()

    assert json_schema["title"] == "OrderIntent"
    assert "intent_id" in json_schema["properties"]


def test_approved_order_accepts_valid_payload() -> None:
    order = ApprovedOrder.model_validate(_approved_payload())

    assert order.quantity == Decimal("10")
    assert order.limit_price == Decimal("0.43")
    assert order.account_id == "acct_paper_001"


def test_approved_order_rejects_float_limit_price() -> None:
    with pytest.raises(TypeError, match="float input"):
        ApprovedOrder.model_validate(_approved_payload(limit_price=0.43))


def test_approved_order_limit_order_requires_limit_price() -> None:
    with pytest.raises(ValidationError, match="limit orders require limit_price"):
        ApprovedOrder.model_validate(_approved_payload(limit_price=None))


def test_approved_order_rejects_post_only_market_order() -> None:
    with pytest.raises(ValidationError, match="post_only is invalid"):
        ApprovedOrder.model_validate(_approved_payload(order_type=OrderType.MARKET, post_only=True))


def test_approved_order_rejects_expired_approval_window() -> None:
    with pytest.raises(ValidationError, match="approval_expires_at must be after"):
        ApprovedOrder.model_validate(_approved_payload(approval_expires_at="2026-07-28T15:00:00Z"))


def test_approved_order_rejects_invalid_account_identifier() -> None:
    with pytest.raises(ValidationError, match="AccountId must start"):
        ApprovedOrder.model_validate(_approved_payload(account_id="paper_001"))


def test_approved_order_json_round_trip_preserves_values() -> None:
    order = ApprovedOrder.model_validate_json(json.dumps(_approved_payload()))

    assert ApprovedOrder.model_validate_json(canonical_json(order)) == order


def test_approved_order_json_schema_generation() -> None:
    json_schema = ApprovedOrder.model_json_schema()

    assert json_schema["title"] == "ApprovedOrder"
    assert "risk_decision_id" in json_schema["properties"]


def test_order_schema_registry_entries_exist() -> None:
    assert get_schema_model("order_intent", 1) is OrderIntent
    assert get_schema_model("approved_order", 1) is ApprovedOrder
    assert (
        get_schema_registration("approved_order", 1).model_path
        == "pmrp.schemas.orders.ApprovedOrder"
    )
