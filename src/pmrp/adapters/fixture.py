"""Deterministic fixture-backed exchange adapter."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from enum import StrEnum
from json import JSONDecodeError
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from pmrp.adapters.base import (
    AdapterAmbiguousOrderSubmissionError,
    AdapterAuthenticationError,
    AdapterCapabilities,
    AdapterEndpointCategory,
    AdapterProtocolError,
    AdapterRateLimitDecision,
    AdapterRateLimitError,
    AdapterRateLimitRule,
    AdapterSequenceGapError,
    AdapterTimeoutError,
    MarketListRequest,
    MarketSubscription,
    RawBalance,
    RawExchangeEvent,
    RawFill,
    RawMarket,
    RawOpenOrder,
    RawPosition,
    evaluate_rate_limit,
)
from pmrp.clock import Clock
from pmrp.schemas.enums import Environment, HealthStatus, OrderType, TimeInForce
from pmrp.schemas.orders import (
    CancelOrderAcknowledgement,
    CancelOrderRequest,
    ExchangeOrderAcknowledgement,
    ExchangeOrderRequest,
)
from pmrp.schemas.system import AdapterHealth


class FixtureAdapterFailureMode(StrEnum):
    """Deterministic failure modes for adapter contract tests."""

    AUTHENTICATION = "authentication"
    AMBIGUOUS_SUBMISSION = "ambiguous_submission"
    MALFORMED_PAYLOAD = "malformed_payload"
    SEQUENCE_GAP = "sequence_gap"
    TIMEOUT = "timeout"


class FixtureAdapter:
    """Deterministic adapter implementation backed by redacted JSON fixtures."""

    def __init__(
        self,
        *,
        fixtures_path: Path,
        clock: Clock,
        exchange: str = "fixture",
        environment: Environment = Environment.TEST,
        capabilities: AdapterCapabilities | None = None,
        failure_mode: FixtureAdapterFailureMode | None = None,
        rate_limit_rule: AdapterRateLimitRule | None = None,
        rate_limit_remaining: int | None = None,
    ) -> None:
        self._fixtures_path = fixtures_path
        self._clock = clock
        self._exchange = exchange
        self._environment = environment
        self._capabilities = capabilities or _default_capabilities(exchange)
        self._failure_mode = failure_mode
        self._rate_limit_rule = rate_limit_rule
        self._rate_limit_remaining = rate_limit_remaining
        self._last_rate_limit_decision: AdapterRateLimitDecision | None = None

        self._connected = False
        self._authenticated = False
        self._subscriptions_active = False
        self._submitted_orders: dict[str, ExchangeOrderAcknowledgement] = {}
        self._cancelled_orders: dict[str, CancelOrderAcknowledgement] = {}

        self._markets = _load_fixture_sequence(
            fixtures_path,
            "markets.json",
            TypeAdapter(tuple[RawMarket, ...]),
        )
        self._stream_events = _load_fixture_sequence(
            fixtures_path,
            "stream.json",
            TypeAdapter(tuple[RawExchangeEvent, ...]),
        )
        self._open_orders = _load_fixture_sequence(
            fixtures_path,
            "open_orders.json",
            TypeAdapter(tuple[RawOpenOrder, ...]),
        )
        self._positions = _load_fixture_sequence(
            fixtures_path,
            "positions.json",
            TypeAdapter(tuple[RawPosition, ...]),
        )
        self._balances = _load_fixture_sequence(
            fixtures_path,
            "balances.json",
            TypeAdapter(tuple[RawBalance, ...]),
        )
        self._fills = _load_fixture_sequence(
            fixtures_path,
            "fills.json",
            TypeAdapter(tuple[RawFill, ...]),
        )

    @property
    def capabilities(self) -> AdapterCapabilities:
        return self._capabilities

    @property
    def last_rate_limit_decision(self) -> AdapterRateLimitDecision | None:
        return self._last_rate_limit_decision

    async def connect(self) -> None:
        if self._failure_mode is FixtureAdapterFailureMode.AUTHENTICATION:
            raise AdapterAuthenticationError(
                "fixture adapter authentication failed",
                exchange=self._exchange,
                endpoint_category=AdapterEndpointCategory.AUTHENTICATION,
            )
        self._connected = True
        self._authenticated = True

    async def disconnect(self) -> None:
        self._connected = False
        self._authenticated = False
        self._subscriptions_active = False

    async def health(self) -> AdapterHealth:
        checked_at = self._clock.now()
        healthy = self._connected and self._authenticated
        return AdapterHealth(
            exchange=self._exchange,
            environment=self._environment,
            status=HealthStatus.HEALTHY if healthy else HealthStatus.UNHEALTHY,
            connected=self._connected,
            authenticated=self._authenticated,
            subscriptions_active=self._subscriptions_active,
            last_message_at=checked_at if self._subscriptions_active else None,
            last_heartbeat_at=checked_at if self._connected else None,
            last_reconciliation_at=None,
            market_data_fresh=self._subscriptions_active,
            trading_gate_open=False,
            reconnect_attempts=0,
            message="Connected." if healthy else "Disconnected.",
        )

    async def list_markets(self, request: MarketListRequest) -> Sequence[RawMarket]:
        self._ensure_connected(AdapterEndpointCategory.MARKET_DATA)
        self._validate_scope(request.exchange, request.environment)
        self._raise_configured_failure(AdapterEndpointCategory.MARKET_DATA, "list_markets")
        self._check_rate_limit(AdapterEndpointCategory.MARKET_DATA, "list_markets")
        return self._markets

    def subscribe_market_data(
        self,
        subscriptions: Sequence[MarketSubscription],
    ) -> AsyncIterator[RawExchangeEvent]:
        async def event_stream() -> AsyncIterator[RawExchangeEvent]:
            self._ensure_connected(AdapterEndpointCategory.STREAM)
            self._raise_configured_failure(AdapterEndpointCategory.STREAM, "subscribe_market_data")
            if not subscriptions:
                msg = "fixture adapter requires at least one market-data subscription"
                raise AdapterProtocolError(
                    msg,
                    exchange=self._exchange,
                    endpoint_category=AdapterEndpointCategory.STREAM,
                )
            for subscription in subscriptions:
                self._validate_scope(subscription.exchange, subscription.environment)
            self._subscriptions_active = True
            previous_sequence: int | None = None
            for event in self._stream_events:
                if self._failure_mode is FixtureAdapterFailureMode.SEQUENCE_GAP:
                    raise AdapterSequenceGapError(
                        "fixture adapter sequence gap detected",
                        exchange=self._exchange,
                        endpoint_category=AdapterEndpointCategory.STREAM,
                    )
                if (
                    previous_sequence is not None
                    and event.sequence is not None
                    and event.sequence != previous_sequence + 1
                ):
                    raise AdapterSequenceGapError(
                        "fixture adapter sequence gap detected",
                        exchange=self._exchange,
                        endpoint_category=AdapterEndpointCategory.STREAM,
                    )
                previous_sequence = event.sequence
                yield event

        return event_stream()

    async def place_order(
        self,
        request: ExchangeOrderRequest,
    ) -> ExchangeOrderAcknowledgement:
        self._ensure_connected(AdapterEndpointCategory.ORDERS)
        if self._failure_mode is FixtureAdapterFailureMode.AMBIGUOUS_SUBMISSION:
            raise AdapterAmbiguousOrderSubmissionError(
                "fixture adapter order submission status is ambiguous",
                exchange=self._exchange,
                endpoint_category=AdapterEndpointCategory.ORDERS,
                request_id=request.idempotency_key,
            )
        self._raise_configured_failure(AdapterEndpointCategory.ORDERS, "place_order")
        self._check_rate_limit(AdapterEndpointCategory.ORDERS, "place_order")
        existing = self._submitted_orders.get(request.idempotency_key)
        if existing is not None:
            return existing
        acknowledgement = ExchangeOrderAcknowledgement(
            order_id=request.order_id,
            client_order_id=request.client_order_id,
            exchange_order_id=f"fixture-{request.client_order_id}",
            exchange=request.exchange,
            account_id=request.account_id,
            accepted=True,
            exchange_status="accepted",
            rejection_code=None,
            rejection_message=None,
            acknowledged_at=self._clock.now(),
            exchange_occurred_at=self._clock.now(),
        )
        self._submitted_orders[request.idempotency_key] = acknowledgement
        return acknowledgement

    async def cancel_order(
        self,
        request: CancelOrderRequest,
    ) -> CancelOrderAcknowledgement:
        self._ensure_connected(AdapterEndpointCategory.ORDERS)
        self._raise_configured_failure(AdapterEndpointCategory.ORDERS, "cancel_order")
        self._check_rate_limit(AdapterEndpointCategory.ORDERS, "cancel_order")
        existing = self._cancelled_orders.get(request.idempotency_key)
        if existing is not None:
            return existing
        acknowledgement = CancelOrderAcknowledgement(
            cancel_request_id=request.cancel_request_id,
            order_id=request.order_id,
            exchange=request.exchange,
            account_id=request.account_id,
            accepted=True,
            exchange_status="cancelled",
            rejection_code=None,
            rejection_message=None,
            acknowledged_at=self._clock.now(),
        )
        self._cancelled_orders[request.idempotency_key] = acknowledgement
        return acknowledgement

    async def get_open_orders(self) -> Sequence[RawOpenOrder]:
        self._ensure_connected(AdapterEndpointCategory.ORDERS)
        return self._open_orders

    async def get_positions(self) -> Sequence[RawPosition]:
        self._ensure_connected(AdapterEndpointCategory.ACCOUNT)
        return self._positions

    async def get_balances(self) -> Sequence[RawBalance]:
        self._ensure_connected(AdapterEndpointCategory.ACCOUNT)
        return self._balances

    async def get_recent_fills(self) -> Sequence[RawFill]:
        self._ensure_connected(AdapterEndpointCategory.ORDERS)
        return self._fills

    def _ensure_connected(self, endpoint_category: AdapterEndpointCategory) -> None:
        if not self._connected or not self._authenticated:
            raise AdapterProtocolError(
                "fixture adapter is not connected",
                exchange=self._exchange,
                endpoint_category=endpoint_category,
            )

    def _validate_scope(self, exchange: str, environment: Environment) -> None:
        if exchange != self._exchange or environment is not self._environment:
            raise AdapterProtocolError(
                "fixture adapter request scope does not match adapter scope",
                exchange=self._exchange,
                endpoint_category=AdapterEndpointCategory.UNKNOWN,
            )

    def _raise_configured_failure(
        self,
        endpoint_category: AdapterEndpointCategory,
        operation: str,
    ) -> None:
        if self._failure_mode is FixtureAdapterFailureMode.TIMEOUT:
            raise AdapterTimeoutError(
                f"fixture adapter timed out during {operation}",
                exchange=self._exchange,
                endpoint_category=endpoint_category,
                retryable=True,
            )
        if self._failure_mode is FixtureAdapterFailureMode.MALFORMED_PAYLOAD:
            raise AdapterProtocolError(
                f"fixture adapter malformed payload during {operation}",
                exchange=self._exchange,
                endpoint_category=endpoint_category,
            )

    def _check_rate_limit(
        self,
        endpoint_category: AdapterEndpointCategory,
        operation: str,
    ) -> None:
        if self._rate_limit_rule is None or self._rate_limit_remaining is None:
            return
        if (
            self._rate_limit_rule.endpoint_category is not endpoint_category
            or self._rate_limit_rule.operation != operation
        ):
            return
        decision = evaluate_rate_limit(
            self._rate_limit_rule,
            remaining=self._rate_limit_remaining,
            decided_at=self._clock.now(),
        )
        self._last_rate_limit_decision = decision
        if decision.allowed:
            self._rate_limit_remaining = decision.remaining_after
            return
        raise AdapterRateLimitError(
            "fixture adapter rate limit exceeded",
            exchange=self._exchange,
            endpoint_category=endpoint_category,
            context={
                "operation": operation,
                "remaining_before": str(decision.remaining_before),
                "rate_limit": str(decision.limit),
            },
        )


def _default_capabilities(exchange: str) -> AdapterCapabilities:
    return AdapterCapabilities(
        exchange=exchange,
        supported_order_types=(OrderType.LIMIT, OrderType.MARKET),
        supported_time_in_force=(TimeInForce.GTC, TimeInForce.IOC),
        supports_post_only=True,
        supports_replace_order=False,
        supports_client_order_id=True,
        supports_streaming_order_updates=False,
        supports_streaming_market_data=True,
        supports_historical_data=False,
        supports_sequence_numbers=True,
        supports_batch_endpoints=False,
        supports_self_trade_controls=False,
        max_batch_size=None,
    )


def _load_fixture_sequence[ModelT](
    fixtures_path: Path,
    filename: str,
    type_adapter: TypeAdapter[tuple[ModelT, ...]],
) -> tuple[ModelT, ...]:
    path = fixtures_path / filename
    try:
        payload = path.read_text(encoding="utf-8")
        return type_adapter.validate_json(payload)
    except FileNotFoundError as exc:
        msg = f"fixture file is missing: {filename}"
        raise AdapterProtocolError(msg, endpoint_category=AdapterEndpointCategory.UNKNOWN) from exc
    except (JSONDecodeError, ValidationError, ValueError, TypeError) as exc:
        msg = f"fixture file is invalid: {filename}"
        raise AdapterProtocolError(msg, endpoint_category=AdapterEndpointCategory.UNKNOWN) from exc
