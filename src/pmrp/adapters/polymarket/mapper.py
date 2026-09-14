"""Polymarket raw-to-canonical market-data mappers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from pydantic import ValidationError

from pmrp.adapters.base.errors import AdapterEndpointCategory, AdapterProtocolError
from pmrp.adapters.polymarket.raw_models import (
    PolymarketRawOrderBookLevel,
    PolymarketRawOrderBookSnapshot,
    PolymarketRawPriceChange,
    PolymarketRawPriceChangeMessage,
)
from pmrp.schemas.enums import ExchangeName, Side
from pmrp.schemas.identifiers import ContractId, MarketId
from pmrp.schemas.market_data import (
    OrderBookDelta,
    OrderBookDeltaAction,
    OrderBookDeltaLevel,
    OrderBookLevel,
    OrderBookSnapshot,
)
from pmrp.schemas.time import parse_utc_datetime

POLYMARKET_ORDER_BOOK_MAPPER_VERSION = "polymarket_order_book_mapper_v1"

type PolymarketMappedOrderBookMessage = OrderBookSnapshot | OrderBookDelta

_MILLISECONDS_PER_SECOND = 1_000
_UNIX_MILLISECONDS_THRESHOLD = 10_000_000_000


def map_polymarket_order_book_message(
    message: PolymarketRawOrderBookSnapshot | PolymarketRawPriceChangeMessage,
    *,
    market_id: MarketId,
    contract_id: ContractId,
    expected_asset_id: str,
    received_at: datetime,
    exchange_occurred_at: datetime | None = None,
    snapshot_reason: str = "initial",
) -> PolymarketMappedOrderBookMessage:
    """Map a Polymarket order-book message into one canonical contract book."""

    if isinstance(message, PolymarketRawOrderBookSnapshot):
        return map_polymarket_order_book_snapshot(
            message,
            market_id=market_id,
            contract_id=contract_id,
            expected_asset_id=expected_asset_id,
            received_at=received_at,
            exchange_occurred_at=exchange_occurred_at,
            snapshot_reason=snapshot_reason,
        )
    return map_polymarket_order_book_delta(
        message,
        market_id=market_id,
        contract_id=contract_id,
        expected_asset_id=expected_asset_id,
        received_at=received_at,
        exchange_occurred_at=exchange_occurred_at,
    )


def map_polymarket_order_book_snapshot(
    message: PolymarketRawOrderBookSnapshot,
    *,
    market_id: MarketId,
    contract_id: ContractId,
    expected_asset_id: str,
    received_at: datetime,
    exchange_occurred_at: datetime | None = None,
    snapshot_reason: str = "initial",
) -> OrderBookSnapshot:
    """Map a Polymarket order-book snapshot for one outcome token.

    Polymarket CLOB book levels are already expressed for the subscribed
    outcome token: ``BUY`` liquidity is canonical bid depth and ``SELL``
    liquidity is canonical ask depth. Polymarket market-channel frames do not
    provide a monotonic sequence, so canonical sequence fields remain ``None``.
    """

    if message.asset_id != _validate_exchange_asset_id(expected_asset_id):
        raise _order_book_mapping_error(
            "Polymarket order-book snapshot asset id does not match expected contract",
            message=message,
            exchange_error_code="polymarket_order_book_asset_mismatch",
        )

    snapshot = _try_map_order_book_snapshot(
        message,
        market_id=market_id,
        contract_id=contract_id,
        received_at=received_at,
        exchange_occurred_at=exchange_occurred_at,
        snapshot_reason=snapshot_reason,
    )
    if snapshot is None:
        raise _order_book_mapping_error(
            "Polymarket order-book snapshot mapping failed",
            message=message,
            exchange_error_code="polymarket_order_book_snapshot_mapping_failed",
        )
    return snapshot


def map_polymarket_order_book_delta(
    message: PolymarketRawPriceChangeMessage,
    *,
    market_id: MarketId,
    contract_id: ContractId,
    expected_asset_id: str,
    received_at: datetime,
    exchange_occurred_at: datetime | None = None,
) -> OrderBookDelta:
    """Map Polymarket price-change entries for one outcome token.

    Polymarket price-change frames may include updates for multiple outcome
    tokens. The caller must pass the exchange token id belonging to the
    canonical contract; updates for other tokens are ignored.
    """

    expected_asset_id = _validate_exchange_asset_id(expected_asset_id)
    token_changes = tuple(
        change for change in message.price_changes if change.asset_id == expected_asset_id
    )
    if not token_changes:
        raise _price_change_mapping_error(
            "Polymarket price-change message did not include expected contract token",
            message=message,
            expected_asset_id=expected_asset_id,
            exchange_error_code="polymarket_price_change_asset_missing",
        )

    delta = _try_map_order_book_delta(
        message,
        token_changes=token_changes,
        market_id=market_id,
        contract_id=contract_id,
        received_at=received_at,
        exchange_occurred_at=exchange_occurred_at,
    )
    if delta is None:
        raise _price_change_mapping_error(
            "Polymarket order-book delta mapping failed",
            message=message,
            expected_asset_id=expected_asset_id,
            exchange_error_code="polymarket_order_book_delta_mapping_failed",
        )
    return delta


def _try_map_order_book_snapshot(
    message: PolymarketRawOrderBookSnapshot,
    *,
    market_id: MarketId,
    contract_id: ContractId,
    received_at: datetime,
    exchange_occurred_at: datetime | None,
    snapshot_reason: str,
) -> OrderBookSnapshot | None:
    try:
        return OrderBookSnapshot(
            market_id=market_id,
            contract_id=contract_id,
            exchange=ExchangeName.POLYMARKET.value,
            sequence=None,
            exchange_occurred_at=_exchange_occurred_at(
                message.timestamp,
                exchange_occurred_at=exchange_occurred_at,
            ),
            received_at=received_at,
            bids=_map_bid_levels(message.bids),
            asks=_map_ask_levels(message.asks),
            is_valid=True,
            snapshot_reason=snapshot_reason,
        )
    except (TypeError, ValueError, ValidationError):
        return None


def _try_map_order_book_delta(
    message: PolymarketRawPriceChangeMessage,
    *,
    token_changes: tuple[PolymarketRawPriceChange, ...],
    market_id: MarketId,
    contract_id: ContractId,
    received_at: datetime,
    exchange_occurred_at: datetime | None,
) -> OrderBookDelta | None:
    try:
        return OrderBookDelta(
            market_id=market_id,
            contract_id=contract_id,
            exchange=ExchangeName.POLYMARKET.value,
            sequence=None,
            previous_sequence=None,
            exchange_occurred_at=_exchange_occurred_at(
                message.timestamp,
                exchange_occurred_at=exchange_occurred_at,
            ),
            received_at=received_at,
            changes=tuple(_map_price_change(change) for change in token_changes),
        )
    except (TypeError, ValueError, ValidationError):
        return None


def _map_bid_levels(
    levels: tuple[PolymarketRawOrderBookLevel, ...],
) -> tuple[OrderBookLevel, ...]:
    return tuple(
        OrderBookLevel(price=level.price, quantity=level.size)
        for level in sorted(levels, key=lambda level: level.price, reverse=True)
    )


def _map_ask_levels(
    levels: tuple[PolymarketRawOrderBookLevel, ...],
) -> tuple[OrderBookLevel, ...]:
    return tuple(
        OrderBookLevel(price=level.price, quantity=level.size)
        for level in sorted(levels, key=lambda level: level.price)
    )


def _map_price_change(change: PolymarketRawPriceChange) -> OrderBookDeltaLevel:
    return OrderBookDeltaLevel(
        side=Side.BUY if change.side == "BUY" else Side.SELL,
        price=change.price,
        quantity=change.size,
        action=(
            OrderBookDeltaAction.DELETE
            if change.size == Decimal("0")
            else OrderBookDeltaAction.UPSERT
        ),
    )


def _exchange_occurred_at(
    timestamp: str | None,
    *,
    exchange_occurred_at: datetime | None,
) -> datetime | None:
    if exchange_occurred_at is not None:
        return parse_utc_datetime(exchange_occurred_at)
    return _parse_polymarket_timestamp(timestamp)


def _parse_polymarket_timestamp(timestamp: str | None) -> datetime | None:
    if timestamp is None:
        return None
    if timestamp.isdecimal():
        raw_epoch = int(timestamp)
        if raw_epoch >= _UNIX_MILLISECONDS_THRESHOLD:
            seconds, milliseconds = divmod(raw_epoch, _MILLISECONDS_PER_SECOND)
            return datetime.fromtimestamp(seconds, tz=UTC) + timedelta(milliseconds=milliseconds)
        return datetime.fromtimestamp(raw_epoch, tz=UTC)
    return parse_utc_datetime(timestamp)


def _validate_exchange_asset_id(value: str) -> str:
    if type(value) is not str:
        msg = "Polymarket expected_asset_id must be a string"
        raise TypeError(msg)
    if value == "" or value.strip() != value:
        msg = "Polymarket expected_asset_id must be nonempty without surrounding whitespace"
        raise ValueError(msg)
    if len(value) > 256:
        msg = "Polymarket expected_asset_id must be at most 256 characters"
        raise ValueError(msg)
    return value


def _order_book_mapping_error(
    safe_message: str,
    *,
    message: PolymarketRawOrderBookSnapshot,
    exchange_error_code: str,
) -> AdapterProtocolError:
    return AdapterProtocolError(
        safe_message,
        exchange=ExchangeName.POLYMARKET.value,
        endpoint_category=AdapterEndpointCategory.STREAM,
        exchange_error_code=exchange_error_code,
        context=_safe_order_book_context(message),
    )


def _price_change_mapping_error(
    safe_message: str,
    *,
    message: PolymarketRawPriceChangeMessage,
    expected_asset_id: str,
    exchange_error_code: str,
) -> AdapterProtocolError:
    return AdapterProtocolError(
        safe_message,
        exchange=ExchangeName.POLYMARKET.value,
        endpoint_category=AdapterEndpointCategory.STREAM,
        exchange_error_code=exchange_error_code,
        context=_safe_price_change_context(
            message,
            expected_asset_id=expected_asset_id,
        ),
    )


def _safe_order_book_context(message: PolymarketRawOrderBookSnapshot) -> dict[str, str]:
    context = {
        "exchange_market_id": message.market,
        "exchange_asset_id": message.asset_id,
    }
    if message.event_type is not None:
        context["event_type"] = message.event_type
    return context


def _safe_price_change_context(
    message: PolymarketRawPriceChangeMessage,
    *,
    expected_asset_id: str,
) -> dict[str, str]:
    return {
        "exchange_market_id": message.market,
        "expected_asset_id": expected_asset_id,
        "price_change_count": str(len(message.price_changes)),
        "event_type": message.event_type,
    }
