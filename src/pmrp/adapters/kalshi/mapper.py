"""Kalshi raw-to-canonical market-data mappers."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import ValidationError

from pmrp.adapters.base.errors import AdapterEndpointCategory, AdapterProtocolError
from pmrp.adapters.kalshi.raw_models import (
    KalshiRawOrderBookLevel,
    KalshiRawOrderBookMessage,
    KalshiRawTrade,
)
from pmrp.schemas.enums import ExchangeName, LiquidityRole, Side
from pmrp.schemas.identifiers import ContractId, MarketId, OutcomeId
from pmrp.schemas.market_data import (
    OrderBookDelta,
    OrderBookDeltaAction,
    OrderBookDeltaLevel,
    OrderBookLevel,
    OrderBookSnapshot,
    Trade,
)

KALSHI_ORDER_BOOK_MAPPER_VERSION = "kalshi_order_book_mapper_v1"
KALSHI_TRADE_MAPPER_VERSION = "kalshi_trade_mapper_v1"

type KalshiMappedOrderBookMessage = OrderBookSnapshot | OrderBookDelta
type KalshiTradeOutcomeSide = Literal["yes", "no"]

_CENTS_PER_CONTRACT = Decimal(100)


def map_kalshi_order_book_message(
    message: KalshiRawOrderBookMessage,
    *,
    market_id: MarketId,
    contract_id: ContractId,
    received_at: datetime,
    previous_sequence: int | None = None,
    exchange_occurred_at: datetime | None = None,
    snapshot_reason: str = "initial",
) -> KalshiMappedOrderBookMessage:
    """Map a Kalshi order-book message into the canonical yes-contract book."""

    if message.message_type == "snapshot":
        return map_kalshi_order_book_snapshot(
            message,
            market_id=market_id,
            contract_id=contract_id,
            received_at=received_at,
            exchange_occurred_at=exchange_occurred_at,
            snapshot_reason=snapshot_reason,
        )
    return map_kalshi_order_book_delta(
        message,
        market_id=market_id,
        contract_id=contract_id,
        received_at=received_at,
        previous_sequence=previous_sequence,
        exchange_occurred_at=exchange_occurred_at,
    )


def map_kalshi_order_book_snapshot(
    message: KalshiRawOrderBookMessage,
    *,
    market_id: MarketId,
    contract_id: ContractId,
    received_at: datetime,
    exchange_occurred_at: datetime | None = None,
    snapshot_reason: str = "initial",
) -> OrderBookSnapshot:
    """Map a Kalshi snapshot into a canonical book for the yes contract.

    Kalshi snapshot ``yes`` levels are bids for the yes contract. Kalshi
    snapshot ``no`` levels are bids for the no contract, which are equivalent
    to asks for the yes contract at ``1 - no_price``.
    """

    if message.message_type != "snapshot":
        raise _order_book_mapping_error(
            "Kalshi order-book message is not a snapshot",
            message=message,
            exchange_error_code="kalshi_order_book_wrong_message_type",
        )

    try:
        return OrderBookSnapshot(
            market_id=market_id,
            contract_id=contract_id,
            exchange=ExchangeName.KALSHI.value,
            sequence=message.sequence,
            exchange_occurred_at=exchange_occurred_at,
            received_at=received_at,
            bids=_map_yes_bid_levels(message.yes),
            asks=_map_no_ask_levels(message.no),
            is_valid=True,
            snapshot_reason=snapshot_reason,
        )
    except (TypeError, ValueError, ValidationError) as exc:
        raise _order_book_mapping_error(
            "Kalshi order-book snapshot mapping failed",
            message=message,
            exchange_error_code="kalshi_order_book_snapshot_mapping_failed",
        ) from exc


def map_kalshi_order_book_delta(
    message: KalshiRawOrderBookMessage,
    *,
    market_id: MarketId,
    contract_id: ContractId,
    received_at: datetime,
    previous_sequence: int | None,
    exchange_occurred_at: datetime | None = None,
) -> OrderBookDelta:
    """Map a Kalshi delta into a canonical book update for the yes contract."""

    if message.message_type != "delta":
        raise _order_book_mapping_error(
            "Kalshi order-book message is not a delta",
            message=message,
            exchange_error_code="kalshi_order_book_wrong_message_type",
        )

    try:
        return OrderBookDelta(
            market_id=market_id,
            contract_id=contract_id,
            exchange=ExchangeName.KALSHI.value,
            sequence=message.sequence,
            previous_sequence=previous_sequence,
            exchange_occurred_at=exchange_occurred_at,
            received_at=received_at,
            changes=(_map_delta_level(message),),
        )
    except (TypeError, ValueError, ValidationError) as exc:
        raise _order_book_mapping_error(
            "Kalshi order-book delta mapping failed",
            message=message,
            exchange_error_code="kalshi_order_book_delta_mapping_failed",
        ) from exc


def map_kalshi_trade(
    trade: KalshiRawTrade,
    *,
    market_id: MarketId,
    contract_id: ContractId,
    outcome_id: OutcomeId,
    received_at: datetime,
    outcome_side: KalshiTradeOutcomeSide = "yes",
) -> Trade:
    """Map a Kalshi trade into a canonical observed trade.

    Kalshi reports prices for yes/no binary outcomes. The caller selects which
    canonical outcome the trade should represent; when the direct side price is
    absent, the mapper uses the exact binary complement.
    """

    try:
        return Trade(
            trade_id=f"kalshi:{trade.trade_id}",
            exchange=ExchangeName.KALSHI.value,
            exchange_trade_id=trade.trade_id,
            market_id=market_id,
            contract_id=contract_id,
            outcome_id=outcome_id,
            price=_kalshi_trade_price(trade, outcome_side=outcome_side),
            quantity=Decimal(trade.count),
            aggressor_side=_map_trade_aggressor_side(trade, outcome_side=outcome_side),
            liquidity_role=LiquidityRole.UNKNOWN,
            exchange_occurred_at=trade.created_time,
            received_at=received_at,
            sequence=trade.sequence,
        )
    except (TypeError, ValueError, ValidationError) as exc:
        raise _trade_mapping_error(
            "Kalshi trade mapping failed",
            trade=trade,
            exchange_error_code="kalshi_trade_mapping_failed",
        ) from exc


def _map_yes_bid_levels(
    levels: tuple[KalshiRawOrderBookLevel, ...],
) -> tuple[OrderBookLevel, ...]:
    return tuple(
        OrderBookLevel(
            price=_kalshi_cents_to_decimal(level.price),
            quantity=Decimal(level.quantity),
        )
        for level in sorted(levels, key=lambda level: level.price, reverse=True)
    )


def _map_no_ask_levels(
    levels: tuple[KalshiRawOrderBookLevel, ...],
) -> tuple[OrderBookLevel, ...]:
    return tuple(
        OrderBookLevel(
            price=_kalshi_no_cents_to_yes_ask_decimal(level.price),
            quantity=Decimal(level.quantity),
        )
        for level in sorted(
            levels,
            key=lambda level: _kalshi_no_cents_to_yes_ask_decimal(level.price),
        )
    )


def _map_delta_level(message: KalshiRawOrderBookMessage) -> OrderBookDeltaLevel:
    if message.side is None or message.price is None or message.action is None:
        raise _order_book_mapping_error(
            "Kalshi order-book delta is missing required fields",
            message=message,
            exchange_error_code="kalshi_order_book_delta_missing_fields",
        )

    if message.side == "yes":
        side = Side.BUY
        price = _kalshi_cents_to_decimal(message.price)
    else:
        side = Side.SELL
        price = _kalshi_no_cents_to_yes_ask_decimal(message.price)

    return OrderBookDeltaLevel(
        side=side,
        price=price,
        quantity=_map_delta_quantity(message),
        action=(
            OrderBookDeltaAction.DELETE
            if message.action == "delete"
            else OrderBookDeltaAction.UPSERT
        ),
    )


def _map_delta_quantity(message: KalshiRawOrderBookMessage) -> Decimal:
    if message.action == "delete":
        return Decimal(0)
    if message.quantity is None:
        raise _order_book_mapping_error(
            "Kalshi order-book delta is missing required fields",
            message=message,
            exchange_error_code="kalshi_order_book_delta_missing_fields",
        )
    return Decimal(message.quantity)


def _kalshi_trade_price(
    trade: KalshiRawTrade,
    *,
    outcome_side: KalshiTradeOutcomeSide,
) -> Decimal:
    if outcome_side == "yes":
        if trade.yes_price is not None:
            return _kalshi_cents_to_decimal(trade.yes_price)
        if trade.no_price is not None:
            return _kalshi_no_cents_to_yes_ask_decimal(trade.no_price)
    elif outcome_side == "no":
        if trade.no_price is not None:
            return _kalshi_cents_to_decimal(trade.no_price)
        if trade.yes_price is not None:
            return _kalshi_no_cents_to_yes_ask_decimal(trade.yes_price)
    else:
        raise ValueError("outcome_side must be yes or no")

    raise ValueError("Kalshi trade is missing a mappable price")


def _map_trade_aggressor_side(
    trade: KalshiRawTrade,
    *,
    outcome_side: KalshiTradeOutcomeSide,
) -> Side | None:
    if trade.taker_side is None:
        return None
    if trade.taker_side not in ("yes", "no"):
        raise _trade_mapping_error(
            "Kalshi trade taker side is unsupported",
            trade=trade,
            exchange_error_code="kalshi_trade_taker_side_unsupported",
        )
    if outcome_side not in ("yes", "no"):
        raise ValueError("outcome_side must be yes or no")
    return Side.BUY if trade.taker_side == outcome_side else Side.SELL


def _kalshi_cents_to_decimal(raw_price: int) -> Decimal:
    return Decimal(raw_price) / _CENTS_PER_CONTRACT


def _kalshi_no_cents_to_yes_ask_decimal(raw_price: int) -> Decimal:
    return Decimal(100 - raw_price) / _CENTS_PER_CONTRACT


def _order_book_mapping_error(
    safe_message: str,
    *,
    message: KalshiRawOrderBookMessage,
    exchange_error_code: str,
) -> AdapterProtocolError:
    return AdapterProtocolError(
        safe_message,
        exchange=ExchangeName.KALSHI.value,
        endpoint_category=AdapterEndpointCategory.STREAM,
        exchange_error_code=exchange_error_code,
        context=_safe_order_book_context(message),
    )


def _trade_mapping_error(
    safe_message: str,
    *,
    trade: KalshiRawTrade,
    exchange_error_code: str,
) -> AdapterProtocolError:
    return AdapterProtocolError(
        safe_message,
        exchange=ExchangeName.KALSHI.value,
        endpoint_category=AdapterEndpointCategory.STREAM,
        exchange_error_code=exchange_error_code,
        context=_safe_trade_context(trade),
    )


def _safe_order_book_context(message: KalshiRawOrderBookMessage) -> dict[str, str]:
    context = {
        "exchange_market_id": message.market_ticker,
        "message_type": message.message_type,
    }
    if message.sequence is not None:
        context["sequence"] = str(message.sequence)
    if message.subscription_id is not None:
        context["subscription_id"] = str(message.subscription_id)
    return context


def _safe_trade_context(trade: KalshiRawTrade) -> dict[str, str]:
    context = {
        "exchange_market_id": trade.market_ticker,
        "exchange_trade_id": trade.trade_id,
    }
    if trade.sequence is not None:
        context["sequence"] = str(trade.sequence)
    if trade.subscription_id is not None:
        context["subscription_id"] = str(trade.subscription_id)
    if trade.taker_side is not None:
        context["taker_side"] = trade.taker_side
    return context
