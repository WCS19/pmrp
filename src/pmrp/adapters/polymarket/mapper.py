"""Polymarket raw-to-canonical market-data mappers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256

from pydantic import ValidationError

from pmrp.adapters.base.errors import AdapterEndpointCategory, AdapterProtocolError
from pmrp.adapters.polymarket.raw_models import (
    PolymarketRawOrderBookLevel,
    PolymarketRawOrderBookSnapshot,
    PolymarketRawPriceChange,
    PolymarketRawPriceChangeMessage,
    PolymarketRawTrade,
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
from pmrp.schemas.time import parse_utc_datetime

POLYMARKET_ORDER_BOOK_MAPPER_VERSION = "polymarket_order_book_mapper_v1"
POLYMARKET_TRADE_MAPPER_VERSION = "polymarket_trade_mapper_v1"

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


def map_polymarket_trade(
    trade: PolymarketRawTrade,
    *,
    market_id: MarketId,
    contract_id: ContractId,
    outcome_id: OutcomeId,
    expected_asset_id: str,
    received_at: datetime,
    exchange_occurred_at: datetime | None = None,
) -> Trade:
    """Map a Polymarket trade observation for one canonical outcome token."""

    if trade.asset_id != _validate_exchange_asset_id(expected_asset_id):
        raise _trade_mapping_error(
            "Polymarket trade asset id does not match expected contract",
            trade=trade,
            exchange_error_code="polymarket_trade_asset_mismatch",
        )

    mapped_trade = _try_map_trade(
        trade,
        market_id=market_id,
        contract_id=contract_id,
        outcome_id=outcome_id,
        received_at=received_at,
        exchange_occurred_at=exchange_occurred_at,
    )
    if mapped_trade is None:
        raise _trade_mapping_error(
            "Polymarket trade mapping failed",
            trade=trade,
            exchange_error_code="polymarket_trade_mapping_failed",
        )
    return mapped_trade


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


def _try_map_trade(
    trade: PolymarketRawTrade,
    *,
    market_id: MarketId,
    contract_id: ContractId,
    outcome_id: OutcomeId,
    received_at: datetime,
    exchange_occurred_at: datetime | None,
) -> Trade | None:
    try:
        exchange_trade_id = _polymarket_exchange_trade_id(trade)
        return Trade(
            trade_id=_canonical_polymarket_trade_id(exchange_trade_id),
            exchange=ExchangeName.POLYMARKET.value,
            exchange_trade_id=exchange_trade_id,
            market_id=market_id,
            contract_id=contract_id,
            outcome_id=outcome_id,
            price=trade.price,
            quantity=_required_trade_size(trade),
            aggressor_side=_map_trade_side(trade),
            liquidity_role=LiquidityRole.UNKNOWN,
            exchange_occurred_at=_trade_exchange_occurred_at(
                trade,
                exchange_occurred_at=exchange_occurred_at,
            ),
            received_at=received_at,
            sequence=None,
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


def _trade_exchange_occurred_at(
    trade: PolymarketRawTrade,
    *,
    exchange_occurred_at: datetime | None,
) -> datetime:
    if exchange_occurred_at is not None:
        return parse_utc_datetime(exchange_occurred_at)
    timestamp = trade.timestamp
    if timestamp is None:
        timestamp = trade.match_time
    if timestamp is None:
        timestamp = trade.last_update
    parsed_timestamp = _parse_polymarket_timestamp(timestamp)
    if parsed_timestamp is None:
        msg = "Polymarket trade timestamp is required"
        raise ValueError(msg)
    return parsed_timestamp


def _required_trade_size(trade: PolymarketRawTrade) -> Decimal:
    if trade.size is None:
        msg = "Polymarket trade size is required for canonical trade mapping"
        raise ValueError(msg)
    return trade.size


def _map_trade_side(trade: PolymarketRawTrade) -> Side:
    return Side.BUY if trade.side == "BUY" else Side.SELL


def _polymarket_exchange_trade_id(trade: PolymarketRawTrade) -> str:
    if trade.trade_id is not None:
        return trade.trade_id
    if trade.transaction_hash is not None:
        return trade.transaction_hash
    return f"generated:{_stable_trade_digest(trade)}"


def _canonical_polymarket_trade_id(exchange_trade_id: str) -> str:
    trade_id = f"polymarket:{exchange_trade_id}"
    if len(trade_id) <= 128:
        return trade_id
    return f"polymarket:{sha256(exchange_trade_id.encode()).hexdigest()}"


def _stable_trade_digest(trade: PolymarketRawTrade) -> str:
    digest_input = "|".join(
        (
            trade.market,
            trade.asset_id,
            trade.timestamp or "",
            trade.match_time or "",
            str(trade.price),
            str(trade.size or ""),
            trade.side,
        )
    )
    return sha256(digest_input.encode()).hexdigest()


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


def _trade_mapping_error(
    safe_message: str,
    *,
    trade: PolymarketRawTrade,
    exchange_error_code: str,
) -> AdapterProtocolError:
    return AdapterProtocolError(
        safe_message,
        exchange=ExchangeName.POLYMARKET.value,
        endpoint_category=AdapterEndpointCategory.STREAM,
        exchange_error_code=exchange_error_code,
        context=_safe_trade_context(trade),
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


def _safe_trade_context(trade: PolymarketRawTrade) -> dict[str, str]:
    context = {
        "exchange_market_id": trade.market,
        "exchange_asset_id": trade.asset_id,
    }
    if trade.event_type is not None:
        context["event_type"] = trade.event_type
    if trade.trade_id is not None:
        context["exchange_trade_id"] = trade.trade_id
    if trade.transaction_hash is not None:
        context["transaction_hash"] = trade.transaction_hash
    if trade.status is not None:
        context["status"] = trade.status
    return context
