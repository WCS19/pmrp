"""Typed repository for versioned risk policy limits."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from pmrp.schemas.risk import RiskLimit, RiskLimitScope
from pmrp.schemas.time import parse_utc_datetime
from pmrp.storage.errors import classify_storage_error
from pmrp.storage.models import RiskLimitRow

_RISK_LIMIT_ID_MAX_LENGTH = 128
_TEXT_FILTER_MAX_LENGTH = 128
_DEFAULT_ACTIVE_LIMIT = 500
_MAX_ACTIVE_LIMIT = 5_000


class RiskLimitRepository:
    """Persist and query canonical risk policy limits."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, limit: RiskLimit) -> None:
        """Insert a risk policy limit and flush without committing."""

        row = risk_limit_to_row(limit)
        try:
            self._session.add(row)
            await self._session.flush()
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

    async def get(self, risk_limit_id: str) -> RiskLimit | None:
        """Return a risk limit by its durable limit ID."""

        _validate_risk_limit_id(risk_limit_id)
        statement = select(RiskLimitRow).where(RiskLimitRow.risk_limit_id == risk_limit_id)
        return await self._one_or_none(statement)

    async def list_active(
        self,
        *,
        as_of: datetime,
        scope: RiskLimitScope | None = None,
        scope_id: str | None = None,
        rule_id: str | None = None,
        limit_type: str | None = None,
        limit: int = _DEFAULT_ACTIVE_LIMIT,
    ) -> tuple[RiskLimit, ...]:
        """Return enabled risk limits active at ``as_of`` for optional filters."""

        as_of = parse_utc_datetime(as_of)
        _validate_limit(limit)
        statement = (
            select(RiskLimitRow)
            .where(
                RiskLimitRow.enabled.is_(True),
                RiskLimitRow.effective_at <= as_of,
                or_(RiskLimitRow.expires_at.is_(None), RiskLimitRow.expires_at > as_of),
            )
            .order_by(RiskLimitRow.scope, RiskLimitRow.scope_id, RiskLimitRow.rule_id)
            .limit(limit)
        )
        if scope is not None:
            statement = statement.where(RiskLimitRow.scope == RiskLimitScope(scope).value)
        if scope_id is not None:
            scope_id = _validate_filter_text(scope_id, field_name="risk limit scope_id")
            statement = statement.where(RiskLimitRow.scope_id == scope_id)
        if rule_id is not None:
            rule_id = _validate_filter_text(rule_id, field_name="risk limit rule_id")
            statement = statement.where(RiskLimitRow.rule_id == rule_id)
        if limit_type is not None:
            limit_type = _validate_filter_text(
                limit_type,
                field_name="risk limit limit_type",
            )
            statement = statement.where(RiskLimitRow.limit_type == limit_type)
        return await self._many(statement)

    async def _one_or_none(self, statement: Select[tuple[RiskLimitRow]]) -> RiskLimit | None:
        try:
            result = await self._session.execute(statement)
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

        row = result.scalar_one_or_none()
        if row is None:
            return None
        return risk_limit_from_row(row)

    async def _many(self, statement: Select[tuple[RiskLimitRow]]) -> tuple[RiskLimit, ...]:
        try:
            result = await self._session.execute(statement)
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

        return tuple(risk_limit_from_row(row) for row in result.scalars().all())


def risk_limit_to_row(limit: RiskLimit) -> RiskLimitRow:
    """Map a canonical risk limit into its storage row."""

    return RiskLimitRow(
        risk_limit_id=limit.risk_limit_id,
        rule_id=limit.rule_id,
        rule_version=limit.rule_version,
        scope=limit.scope.value,
        scope_id=limit.scope_id,
        limit_type=limit.limit_type,
        limit_value=limit.limit_value,
        unit=limit.unit,
        effective_at=limit.effective_at,
        expires_at=limit.expires_at,
        enabled=limit.enabled,
        created_by=limit.created_by,
        approved_by=limit.approved_by,
    )


def risk_limit_from_row(row: RiskLimitRow) -> RiskLimit:
    """Map a storage row into a validated canonical risk limit."""

    return RiskLimit(
        risk_limit_id=row.risk_limit_id,
        rule_id=row.rule_id,
        rule_version=row.rule_version,
        scope=RiskLimitScope(row.scope),
        scope_id=row.scope_id,
        limit_type=row.limit_type,
        limit_value=row.limit_value,
        unit=row.unit,
        effective_at=row.effective_at,
        expires_at=row.expires_at,
        enabled=row.enabled,
        created_by=row.created_by,
        approved_by=row.approved_by,
    )


def _validate_risk_limit_id(risk_limit_id: str) -> None:
    if type(risk_limit_id) is not str:
        msg = "risk limit ID must be a string"
        raise TypeError(msg)
    if risk_limit_id == "":
        raise ValueError("risk limit ID must not be empty")
    if len(risk_limit_id) > _RISK_LIMIT_ID_MAX_LENGTH:
        raise ValueError("risk limit ID must be at most 128 characters")


def _validate_filter_text(value: str, *, field_name: str) -> str:
    if type(value) is not str:
        msg = f"{field_name} must be a string"
        raise TypeError(msg)
    if value == "":
        raise ValueError(f"{field_name} must not be empty")
    if len(value) > _TEXT_FILTER_MAX_LENGTH:
        raise ValueError(f"{field_name} must be at most 128 characters")
    return value


def _validate_limit(limit: int) -> None:
    if type(limit) is not int:
        msg = "risk limit list limit must be an integer"
        raise TypeError(msg)
    if limit <= 0:
        raise ValueError("risk limit list limit must be positive")
    if limit > _MAX_ACTIVE_LIMIT:
        raise ValueError("risk limit list limit must be at most 5000")
