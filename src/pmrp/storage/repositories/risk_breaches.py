"""Typed repository for post-trade and operational risk breach persistence."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, Update, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from pmrp.schemas.identifiers import CorrelationId
from pmrp.schemas.risk import RiskBreach, RiskLimitScope
from pmrp.schemas.time import parse_utc_datetime
from pmrp.storage.errors import classify_storage_error
from pmrp.storage.models import RiskBreachRow

_BREACH_ID_MAX_LENGTH = 128
_SEVERITY_MAX_LENGTH = 64
_RESOLUTION_NOTE_MAX_LENGTH = 1024
_DEFAULT_OPEN_LIMIT = 100
_MAX_OPEN_LIMIT = 1_000


class RiskBreachRepository:
    """Persist, query, and resolve canonical risk breach records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, breach: RiskBreach) -> None:
        """Insert a canonical risk breach and flush without committing."""

        row = risk_breach_to_row(breach)
        try:
            self._session.add(row)
            await self._session.flush()
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

    async def get(self, breach_id: str) -> RiskBreach | None:
        """Return a breach by its durable breach ID."""

        _validate_breach_id(breach_id)
        statement = select(RiskBreachRow).where(RiskBreachRow.breach_id == breach_id)
        return await self._one_or_none(statement)

    async def list_open(
        self,
        *,
        severity: str | None = None,
        limit: int = _DEFAULT_OPEN_LIMIT,
    ) -> tuple[RiskBreach, ...]:
        """Return unresolved breaches newest first, optionally filtered by severity."""

        _validate_limit(limit)
        statement = (
            select(RiskBreachRow)
            .where(RiskBreachRow.resolved_at.is_(None))
            .order_by(RiskBreachRow.detected_at.desc())
            .limit(limit)
        )
        if severity is not None:
            severity = _validate_severity(severity)
            statement = statement.where(RiskBreachRow.severity == severity)
        return await self._many(statement)

    async def resolve(
        self,
        breach_id: str,
        *,
        resolved_at: datetime,
        resolution_note: str | None = None,
    ) -> int:
        """Resolve one open breach and return the updated row count."""

        _validate_breach_id(breach_id)
        resolved_at = parse_utc_datetime(resolved_at)
        resolution_note = _validate_resolution_note(resolution_note)
        statement = (
            update(RiskBreachRow)
            .where(
                RiskBreachRow.breach_id == breach_id,
                RiskBreachRow.resolved_at.is_(None),
            )
            .values(
                resolved_at=resolved_at,
                resolution_note=resolution_note,
            )
        )
        return await self._execute_update(statement)

    async def _one_or_none(self, statement: Select[tuple[RiskBreachRow]]) -> RiskBreach | None:
        try:
            result = await self._session.execute(statement)
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

        row = result.scalar_one_or_none()
        if row is None:
            return None
        return risk_breach_from_row(row)

    async def _many(self, statement: Select[tuple[RiskBreachRow]]) -> tuple[RiskBreach, ...]:
        try:
            result = await self._session.execute(statement)
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

        return tuple(risk_breach_from_row(row) for row in result.scalars().all())

    async def _execute_update(self, statement: Update) -> int:
        try:
            result = await self._session.execute(statement)
            await self._session.flush()
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

        return int(getattr(result, "rowcount", 0) or 0)


def risk_breach_to_row(breach: RiskBreach) -> RiskBreachRow:
    """Map a canonical risk breach into its storage row."""

    return RiskBreachRow(
        breach_id=breach.breach_id,
        rule_id=breach.rule_id,
        rule_version=breach.rule_version,
        scope=breach.scope.value,
        scope_id=breach.scope_id,
        severity=breach.severity,
        detected_at=breach.detected_at,
        observed_value=breach.observed_value,
        limit_value=breach.limit_value,
        unit=breach.unit,
        action_taken=breach.action_taken,
        correlation_id=str(breach.correlation_id),
        resolved_at=None,
        resolution_note=None,
    )


def risk_breach_from_row(row: RiskBreachRow) -> RiskBreach:
    """Map a storage row into a validated canonical risk breach."""

    return RiskBreach(
        breach_id=row.breach_id,
        rule_id=row.rule_id,
        rule_version=row.rule_version,
        scope=RiskLimitScope(row.scope),
        scope_id=row.scope_id,
        severity=row.severity,
        detected_at=row.detected_at,
        observed_value=row.observed_value,
        limit_value=row.limit_value,
        unit=row.unit,
        action_taken=row.action_taken,
        correlation_id=CorrelationId(row.correlation_id),
    )


def _validate_breach_id(breach_id: str) -> None:
    if type(breach_id) is not str:
        msg = "risk breach ID must be a string"
        raise TypeError(msg)
    if breach_id == "":
        raise ValueError("risk breach ID must not be empty")
    if len(breach_id) > _BREACH_ID_MAX_LENGTH:
        raise ValueError("risk breach ID must be at most 128 characters")


def _validate_severity(severity: str) -> str:
    if type(severity) is not str:
        msg = "risk breach severity must be a string"
        raise TypeError(msg)
    if severity == "":
        raise ValueError("risk breach severity must not be empty")
    if len(severity) > _SEVERITY_MAX_LENGTH:
        raise ValueError("risk breach severity must be at most 64 characters")
    return severity


def _validate_resolution_note(resolution_note: str | None) -> str | None:
    if resolution_note is None:
        return None
    if type(resolution_note) is not str:
        msg = "risk breach resolution note must be a string"
        raise TypeError(msg)
    if resolution_note == "":
        raise ValueError("risk breach resolution note must not be empty")
    if len(resolution_note) > _RESOLUTION_NOTE_MAX_LENGTH:
        raise ValueError("risk breach resolution note must be at most 1024 characters")
    return resolution_note


def _validate_limit(limit: int) -> None:
    if type(limit) is not int:
        msg = "risk breach list limit must be an integer"
        raise TypeError(msg)
    if limit <= 0:
        raise ValueError("risk breach list limit must be positive")
    if limit > _MAX_OPEN_LIMIT:
        raise ValueError("risk breach list limit must be at most 1000")
