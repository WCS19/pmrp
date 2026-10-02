"""PnL attribution helpers for portfolio accounting journals."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal
from typing import Final

from pmrp.portfolio.errors import PortfolioProjectionError
from pmrp.portfolio.journal import (
    ACCOUNT_FEES_PAID,
    ACCOUNT_REALIZED_TRADING_PNL,
    ACCOUNT_REBATES_RECEIVED,
)
from pmrp.schemas.identifiers import MarketId, StrategyId
from pmrp.schemas.numeric import Money, validate_currency
from pmrp.schemas.portfolio import AccountingJournalEntry, PnlAttribution
from pmrp.schemas.serialization import canonical_sha256

JOURNAL_PNL_ATTRIBUTION_VERSION: Final = "journal_pnl_attribution_v1"

_ZERO = Decimal("0")


def build_journal_pnl_attribution(
    *,
    journal_entries: Iterable[AccountingJournalEntry],
    currency: str,
    starts_at: datetime,
    ends_at: datetime,
    attribution_id: str | None = None,
    strategy_id: StrategyId | None = None,
    market_id: MarketId | None = None,
    exchange: str | None = None,
    unrealized_pnl_change: Money | None = None,
    slippage: Money | None = None,
    settlement_pnl: Money | None = None,
) -> PnlAttribution:
    """Build a canonical PnL attribution from balanced accounting journals."""

    validated_currency = validate_currency(currency)
    entries = tuple(journal_entries)
    _validate_unique_journal_entry_ids(entries)
    _validate_journal_period(entries, starts_at=starts_at, ends_at=ends_at)

    realized_trading_pnl = Money(
        amount=-_sum_account(
            entries,
            account_code=ACCOUNT_REALIZED_TRADING_PNL,
            currency=validated_currency,
        ),
        currency=validated_currency,
    )
    fees = Money(
        amount=_sum_account(
            entries,
            account_code=ACCOUNT_FEES_PAID,
            currency=validated_currency,
        ),
        currency=validated_currency,
    )
    rebates = Money(
        amount=-_sum_account(
            entries,
            account_code=ACCOUNT_REBATES_RECEIVED,
            currency=validated_currency,
        ),
        currency=validated_currency,
    )
    _validate_nonnegative(fees, field_name="fees")
    _validate_nonnegative(rebates, field_name="rebates")

    zero = _zero_money(validated_currency)
    unrealized = _validate_money_or_default(
        unrealized_pnl_change,
        currency=validated_currency,
        field_name="unrealized_pnl_change",
        default=zero,
    )
    validated_slippage = _validate_optional_money(
        slippage,
        currency=validated_currency,
        field_name="slippage",
    )
    validated_settlement = _validate_optional_money(
        settlement_pnl,
        currency=validated_currency,
        field_name="settlement_pnl",
    )

    return PnlAttribution(
        attribution_id=attribution_id
        or derive_journal_pnl_attribution_id(
            journal_entries=entries,
            currency=validated_currency,
            starts_at=starts_at,
            ends_at=ends_at,
            strategy_id=strategy_id,
            market_id=market_id,
            exchange=exchange,
        ),
        strategy_id=strategy_id,
        market_id=market_id,
        exchange=exchange,
        starts_at=starts_at,
        ends_at=ends_at,
        realized_trading_pnl=realized_trading_pnl,
        unrealized_pnl_change=unrealized,
        fees=fees,
        rebates=rebates,
        slippage=validated_slippage,
        settlement_pnl=validated_settlement,
        total_pnl=Money(
            amount=(
                realized_trading_pnl.amount
                + unrealized.amount
                - fees.amount
                + rebates.amount
                + _optional_amount(validated_slippage)
                + _optional_amount(validated_settlement)
            ),
            currency=validated_currency,
        ),
        calculation_version=JOURNAL_PNL_ATTRIBUTION_VERSION,
    )


def derive_journal_pnl_attribution_id(
    *,
    journal_entries: Iterable[AccountingJournalEntry],
    currency: str,
    starts_at: datetime,
    ends_at: datetime,
    strategy_id: StrategyId | None = None,
    market_id: MarketId | None = None,
    exchange: str | None = None,
) -> str:
    """Derive a stable PnL attribution identifier from period and journals."""

    validated_currency = validate_currency(currency)
    journal_entry_ids = sorted(str(entry.journal_entry_id) for entry in journal_entries)
    digest = canonical_sha256(
        {
            "calculation_version": JOURNAL_PNL_ATTRIBUTION_VERSION,
            "currency": validated_currency,
            "ends_at": ends_at,
            "exchange": exchange,
            "journal_entry_ids": journal_entry_ids,
            "market_id": market_id,
            "starts_at": starts_at,
            "strategy_id": strategy_id,
        }
    ).removeprefix("sha256:")
    return f"pnl_{digest[:32]}"


def _sum_account(
    journal_entries: Iterable[AccountingJournalEntry],
    *,
    account_code: str,
    currency: str,
) -> Decimal:
    return sum(
        (
            line.amount
            for entry in journal_entries
            for line in entry.lines
            if line.account_code == account_code and line.currency == currency
        ),
        start=_ZERO,
    )


def _validate_unique_journal_entry_ids(entries: tuple[AccountingJournalEntry, ...]) -> None:
    seen: set[str] = set()
    for entry in entries:
        if entry.journal_entry_id in seen:
            msg = "journal entries must not contain duplicate journal_entry_id values"
            raise PortfolioProjectionError(msg)
        seen.add(entry.journal_entry_id)


def _validate_journal_period(
    entries: tuple[AccountingJournalEntry, ...],
    *,
    starts_at: datetime,
    ends_at: datetime,
) -> None:
    if ends_at <= starts_at:
        msg = "ends_at must be after starts_at"
        raise PortfolioProjectionError(msg)
    for entry in entries:
        if entry.occurred_at < starts_at or entry.occurred_at >= ends_at:
            msg = "journal entry occurred_at must fall within [starts_at, ends_at)"
            raise PortfolioProjectionError(msg)


def _validate_money_or_default(
    value: Money | None,
    *,
    currency: str,
    field_name: str,
    default: Money,
) -> Money:
    if value is None:
        return default
    _validate_money(value, currency=currency, field_name=field_name)
    return value


def _validate_optional_money(
    value: Money | None,
    *,
    currency: str,
    field_name: str,
) -> Money | None:
    if value is None:
        return None
    _validate_money(value, currency=currency, field_name=field_name)
    return value


def _validate_money(value: Money, *, currency: str, field_name: str) -> None:
    if value.currency != currency:
        msg = f"{field_name} currency must match attribution currency"
        raise PortfolioProjectionError(msg)


def _validate_nonnegative(value: Money, *, field_name: str) -> None:
    if value.amount < _ZERO:
        msg = f"{field_name} amount must be nonnegative"
        raise PortfolioProjectionError(msg)


def _zero_money(currency: str) -> Money:
    return Money(amount=_ZERO, currency=currency)


def _optional_amount(value: Money | None) -> Decimal:
    if value is None:
        return _ZERO
    return value.amount
