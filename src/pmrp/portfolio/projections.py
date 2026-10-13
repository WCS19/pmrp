"""Portfolio projection workflows built from accounting primitives."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from datetime import datetime

from pmrp.portfolio.errors import PortfolioProjectionError
from pmrp.portfolio.journal import build_fill_journal_entry
from pmrp.portfolio.positions import PositionProjectionResult, apply_fill_to_position
from pmrp.schemas.identifiers import EventId, FillId, PositionId
from pmrp.schemas.orders import Fill
from pmrp.schemas.portfolio import AccountingJournalEntry, Position


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
