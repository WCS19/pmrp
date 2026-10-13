"""Portfolio projection workflows built from accounting primitives."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from pmrp.portfolio.errors import PortfolioProjectionError
from pmrp.portfolio.journal import build_fill_journal_entry
from pmrp.portfolio.positions import PositionProjectionResult, apply_fill_to_position
from pmrp.schemas.identifiers import EventId, FillId, PositionId
from pmrp.schemas.numeric import Money
from pmrp.schemas.orders import Fill
from pmrp.schemas.portfolio import AccountingJournalEntry, CashBalance, PortfolioSnapshot, Position

_ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class FillApplicationResult:
    """Result of idempotently applying a fill to portfolio projections."""

    position: Position | None
    position_projection: PositionProjectionResult | None
    journal_entry: AccountingJournalEntry | None
    applied_fill_ids: frozenset[FillId]
    applied: bool
    duplicate_fill: bool


@dataclass(frozen=True, slots=True)
class FillBatchApplicationResult:
    """Result of deterministically applying a batch of fills once."""

    position: Position | None
    fill_results: tuple[FillApplicationResult, ...]
    journal_entries: tuple[AccountingJournalEntry, ...]
    applied_fill_ids: frozenset[FillId]
    applied_count: int
    duplicate_fill_count: int


def apply_fill_once(
    *,
    position: Position | None,
    fill: Fill,
    applied_fill_ids: AbstractSet[FillId],
    currency: str,
    source_event_id: EventId,
    created_at: datetime,
    position_id: PositionId | None = None,
) -> FillApplicationResult:
    """Apply a fill once and return a no-op result for duplicate fill IDs."""

    existing_fill_ids = frozenset(applied_fill_ids)
    if fill.fill_id in existing_fill_ids:
        return FillApplicationResult(
            position=position,
            position_projection=None,
            journal_entry=None,
            applied_fill_ids=existing_fill_ids,
            applied=False,
            duplicate_fill=True,
        )

    projection = apply_fill_to_position(
        position,
        fill,
        currency=currency,
        position_id=position_id,
    )
    journal_entry = build_fill_journal_entry(
        fill=fill,
        projection=projection,
        source_event_id=source_event_id,
        created_at=created_at,
    )
    return FillApplicationResult(
        position=projection.position,
        position_projection=projection,
        journal_entry=journal_entry,
        applied_fill_ids=existing_fill_ids | {fill.fill_id},
        applied=True,
        duplicate_fill=False,
    )


def apply_fills_once(
    *,
    position: Position | None,
    fills: Iterable[Fill],
    applied_fill_ids: AbstractSet[FillId],
    currency: str,
    source_event_ids: Mapping[FillId, EventId],
    created_at: datetime,
    position_id: PositionId | None = None,
) -> FillBatchApplicationResult:
    """Apply a fill batch once in deterministic exchange-time order."""

    fill_batch = tuple(fills)
    _validate_fill_batch(fill_batch, source_event_ids=source_event_ids)
    current_position = position
    current_fill_ids = frozenset(applied_fill_ids)
    results: list[FillApplicationResult] = []
    journals: list[AccountingJournalEntry] = []

    for fill in sorted(fill_batch, key=_fill_order_key):
        result = apply_fill_once(
            position=current_position,
            fill=fill,
            applied_fill_ids=current_fill_ids,
            currency=currency,
            source_event_id=source_event_ids[fill.fill_id],
            created_at=created_at,
            position_id=position_id,
        )
        current_position = result.position
        current_fill_ids = result.applied_fill_ids
        results.append(result)
        if result.journal_entry is not None:
            journals.append(result.journal_entry)

    return FillBatchApplicationResult(
        position=current_position,
        fill_results=tuple(results),
        journal_entries=tuple(journals),
        applied_fill_ids=current_fill_ids,
        applied_count=sum(1 for result in results if result.applied),
        duplicate_fill_count=sum(1 for result in results if result.duplicate_fill),
    )


def _validate_fill_batch(
    fills: tuple[Fill, ...],
    *,
    source_event_ids: Mapping[FillId, EventId],
) -> None:
    fill_by_id: dict[FillId, Fill] = {}
    for fill in fills:
        previous = fill_by_id.get(fill.fill_id)
        if previous is not None and previous != fill:
            msg = "duplicate fill_id has conflicting fill payload"
            raise PortfolioProjectionError(msg)
        fill_by_id[fill.fill_id] = fill

    missing_source_event_ids = sorted(
        str(fill_id) for fill_id in fill_by_id if fill_id not in source_event_ids
    )
    if missing_source_event_ids:
        msg = "source_event_ids must contain every fill_id in the batch"
        raise PortfolioProjectionError(msg)


def _fill_order_key(fill: Fill) -> tuple[datetime, datetime, str]:
    return (fill.exchange_occurred_at, fill.received_at, str(fill.fill_id))


def build_portfolio_snapshot(
    *,
    portfolio_id: str,
    positions: Iterable[Position],
    balances: Iterable[CashBalance],
    captured_at: datetime,
    reconciliation_status: str,
) -> PortfolioSnapshot:
    """Build a deterministic portfolio snapshot from projected state."""

    position_tuple = tuple(sorted(positions, key=lambda position: str(position.position_id)))
    balance_tuple = tuple(sorted(balances, key=lambda balance: balance.balance_id))
    _validate_snapshot_horizon(
        positions=position_tuple,
        balances=balance_tuple,
        captured_at=captured_at,
    )

    return PortfolioSnapshot(
        portfolio_id=portfolio_id,
        captured_at=captured_at,
        positions=position_tuple,
        balances=balance_tuple,
        realized_pnl=_sum_position_money(
            position_tuple,
            field_name="realized_pnl",
        ),
        unrealized_pnl=_sum_position_money(
            position_tuple,
            field_name="unrealized_pnl",
        ),
        gross_exposure=_sum_position_exposure(position_tuple, gross=True),
        net_exposure=_sum_position_exposure(position_tuple, gross=False),
        reconciliation_status=reconciliation_status,
    )


def _validate_snapshot_horizon(
    *,
    positions: tuple[Position, ...],
    balances: tuple[CashBalance, ...],
    captured_at: datetime,
) -> None:
    for position in positions:
        if position.last_updated_at > captured_at:
            msg = "position last_updated_at must not be after snapshot captured_at"
            raise PortfolioProjectionError(msg)
        _position_currency(position)
        if position.quantity != _ZERO and position.average_entry_price is None:
            msg = "nonzero position requires average_entry_price for snapshot exposure"
            raise PortfolioProjectionError(msg)

    for balance in balances:
        if balance.captured_at > captured_at:
            msg = "balance captured_at must not be after snapshot captured_at"
            raise PortfolioProjectionError(msg)


def _sum_position_money(
    positions: tuple[Position, ...],
    *,
    field_name: str,
) -> tuple[Money, ...]:
    totals: defaultdict[str, Decimal] = defaultdict(lambda: _ZERO)
    for position in positions:
        money = getattr(position, field_name)
        if not isinstance(money, Money):
            msg = f"position {field_name} must be Money"
            raise PortfolioProjectionError(msg)
        totals[money.currency] += money.amount
    return _money_totals(totals)


def _sum_position_exposure(
    positions: tuple[Position, ...],
    *,
    gross: bool,
) -> tuple[Money, ...]:
    totals: defaultdict[str, Decimal] = defaultdict(lambda: _ZERO)
    for position in positions:
        currency = _position_currency(position)
        exposure = _position_exposure(position)
        if gross:
            exposure = abs(exposure)
        totals[currency] += exposure
    return _money_totals(totals)


def _position_currency(position: Position) -> str:
    currency = position.realized_pnl.currency
    money_fields = (
        ("unrealized_pnl", position.unrealized_pnl),
        ("fees_paid", position.fees_paid),
        ("rebates_received", position.rebates_received),
    )
    for field_name, money in money_fields:
        if money.currency != currency:
            msg = f"position {field_name} currency must match realized_pnl currency"
            raise PortfolioProjectionError(msg)
    return currency


def _position_exposure(position: Position) -> Decimal:
    if position.quantity == _ZERO:
        return _ZERO
    if position.average_entry_price is None:
        msg = "nonzero position requires average_entry_price for snapshot exposure"
        raise PortfolioProjectionError(msg)
    return position.quantity * position.average_entry_price


def _money_totals(totals: Mapping[str, Decimal]) -> tuple[Money, ...]:
    return tuple(Money(amount=totals[currency], currency=currency) for currency in sorted(totals))
