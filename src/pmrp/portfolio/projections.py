"""Portfolio projection workflows built from accounting primitives."""

from __future__ import annotations

from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from datetime import datetime

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
