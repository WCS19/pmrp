from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from pmrp.schemas.enums import OrderStatus, OrderType, Side, TimeInForce
from pmrp.schemas.orders import Order
from pmrp.schemas.serialization import canonical_sha256

pytestmark = pytest.mark.property


@st.composite
def _order_quantities(
    draw: st.DrawFn,
) -> tuple[Decimal, Decimal, Decimal]:
    quantity = draw(
        st.decimals(
            min_value=Decimal("0.0001"),
            max_value=Decimal("1000000"),
            allow_nan=False,
            allow_infinity=False,
            places=4,
        )
    )
    filled_quantity = draw(
        st.decimals(
            min_value=Decimal("0"),
            max_value=quantity,
            allow_nan=False,
            allow_infinity=False,
            places=4,
        )
    )
    return quantity, filled_quantity, quantity - filled_quantity


def _order_payload(
    *,
    quantity: Decimal,
    filled_quantity: Decimal,
    remaining_quantity: Decimal,
) -> dict[str, object]:
    return {
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
        "quantity": str(quantity),
        "filled_quantity": str(filled_quantity),
        "remaining_quantity": str(remaining_quantity),
        "limit_price": "0.43",
        "average_fill_price": "0.42" if filled_quantity > Decimal("0") else None,
        "order_type": OrderType.LIMIT,
        "time_in_force": TimeInForce.GTC,
        "post_only": True,
        "reduce_only": False,
        "status": (
            OrderStatus.PARTIALLY_FILLED if filled_quantity > Decimal("0") else OrderStatus.ACCEPTED
        ),
        "client_order_id": "client-order-001",
        "exchange_order_id": "exchange-order-001",
        "created_at": "2026-07-28T15:00:00Z",
        "submitted_at": "2026-07-28T15:00:01Z",
        "accepted_at": "2026-07-28T15:00:02Z",
        "last_updated_at": "2026-07-28T15:00:03Z",
        "expires_at": "2026-07-28T15:10:00Z",
        "aggregate_version": 3,
    }


@given(quantities=_order_quantities())
def test_order_accepts_exact_generated_fill_accounting(
    quantities: tuple[Decimal, Decimal, Decimal],
) -> None:
    quantity, filled_quantity, remaining_quantity = quantities

    order = Order.model_validate(
        _order_payload(
            quantity=quantity,
            filled_quantity=filled_quantity,
            remaining_quantity=remaining_quantity,
        )
    )

    assert order.filled_quantity + order.remaining_quantity == order.quantity


@given(quantities=_order_quantities())
def test_order_rejects_generated_fill_accounting_mismatch(
    quantities: tuple[Decimal, Decimal, Decimal],
) -> None:
    quantity, filled_quantity, remaining_quantity = quantities

    with pytest.raises(ValidationError, match="filled_quantity plus remaining_quantity"):
        Order.model_validate(
            _order_payload(
                quantity=quantity,
                filled_quantity=filled_quantity,
                remaining_quantity=remaining_quantity + Decimal("0.0001"),
            )
        )


@given(quantities=_order_quantities())
def test_order_hash_is_stable_for_generated_accounting(
    quantities: tuple[Decimal, Decimal, Decimal],
) -> None:
    quantity, filled_quantity, remaining_quantity = quantities
    order = Order.model_validate(
        _order_payload(
            quantity=quantity,
            filled_quantity=filled_quantity,
            remaining_quantity=remaining_quantity,
        )
    )

    assert canonical_sha256(order) == canonical_sha256(order)
