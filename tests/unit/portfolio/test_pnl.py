"""Unit tests for portfolio PnL attribution helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.portfolio import (
    ACCOUNT_FEES_PAID,
    ACCOUNT_REALIZED_TRADING_PNL,
    ACCOUNT_REBATES_RECEIVED,
    JOURNAL_PNL_ATTRIBUTION_VERSION,
    PortfolioProjectionError,
    build_journal_pnl_attribution,
    derive_journal_pnl_attribution_id,
)
from pmrp.schemas.identifiers import EventId, MarketId, StrategyId
from pmrp.schemas.numeric import Money
from pmrp.schemas.portfolio import AccountingJournalEntry, JournalLine

pytestmark = pytest.mark.unit

STARTS_AT = datetime(2026, 9, 25, 14, 0, tzinfo=UTC)
ENDS_AT = datetime(2026, 9, 25, 15, 0, tzinfo=UTC)
OCCURRED_AT = datetime(2026, 9, 25, 14, 5, tzinfo=UTC)
CREATED_AT = datetime(2026, 9, 25, 14, 5, 1, tzinfo=UTC)


def test_build_journal_pnl_attribution_converts_journal_signs_to_economic_pnl() -> None:
    journal = _journal(
        lines=_pnl_lines(
            realized=Decimal("0.80"),
            fees=Decimal("0.02"),
            rebates=Decimal("0.01"),
        )
    )

    attribution = build_journal_pnl_attribution(
        journal_entries=(journal,),
        currency="USD",
        starts_at=STARTS_AT,
        ends_at=ENDS_AT,
        strategy_id=StrategyId("strat_pnl_001"),
        market_id=MarketId("mkt_pnl_001"),
        exchange="kalshi",
        unrealized_pnl_change=_money("0.05"),
        slippage=_money("-0.03"),
        settlement_pnl=_money("0.10"),
    )

    assert attribution.attribution_id == derive_journal_pnl_attribution_id(
        journal_entries=(journal,),
        currency="USD",
        starts_at=STARTS_AT,
        ends_at=ENDS_AT,
        strategy_id=StrategyId("strat_pnl_001"),
        market_id=MarketId("mkt_pnl_001"),
        exchange="kalshi",
    )
    assert attribution.realized_trading_pnl == _money("0.80")
    assert attribution.unrealized_pnl_change == _money("0.05")
    assert attribution.fees == _money("0.02")
    assert attribution.rebates == _money("0.01")
    assert attribution.slippage == _money("-0.03")
    assert attribution.settlement_pnl == _money("0.10")
    assert attribution.total_pnl == _money("0.91")
    assert attribution.calculation_version == JOURNAL_PNL_ATTRIBUTION_VERSION


def test_build_journal_pnl_attribution_supports_realized_losses() -> None:
    journal = _journal(
        lines=_pnl_lines(
            realized=Decimal("-0.30"),
            fees=Decimal("0"),
            rebates=Decimal("0"),
        )
    )

    attribution = build_journal_pnl_attribution(
        journal_entries=(journal,),
        currency="USD",
        starts_at=STARTS_AT,
        ends_at=ENDS_AT,
    )

    assert attribution.realized_trading_pnl == _money("-0.30")
    assert attribution.total_pnl == _money("-0.30")


def test_build_journal_pnl_attribution_sums_multiple_journals() -> None:
    first = _journal(
        journal_entry_id="journal_pnl_first",
        lines=_pnl_lines(
            realized=Decimal("0.80"),
            fees=Decimal("0.02"),
            rebates=Decimal("0"),
        ),
    )
    second = _journal(
        journal_entry_id="journal_pnl_second",
        occurred_at=OCCURRED_AT + timedelta(minutes=1),
        created_at=CREATED_AT + timedelta(minutes=1),
        lines=_pnl_lines(
            realized=Decimal("-0.20"),
            fees=Decimal("0.01"),
            rebates=Decimal("0.04"),
        ),
    )

    attribution = build_journal_pnl_attribution(
        journal_entries=(first, second),
        currency="USD",
        starts_at=STARTS_AT,
        ends_at=ENDS_AT,
    )

    assert attribution.realized_trading_pnl == _money("0.60")
    assert attribution.fees == _money("0.03")
    assert attribution.rebates == _money("0.04")
    assert attribution.total_pnl == _money("0.61")


def test_derive_journal_pnl_attribution_id_is_stable_for_journal_order() -> None:
    first = _journal(
        journal_entry_id="journal_pnl_first",
        lines=_pnl_lines(realized=Decimal("0.10"), fees=Decimal("0"), rebates=Decimal("0")),
    )
    second = _journal(
        journal_entry_id="journal_pnl_second",
        lines=_pnl_lines(realized=Decimal("0.20"), fees=Decimal("0"), rebates=Decimal("0")),
    )

    forward = derive_journal_pnl_attribution_id(
        journal_entries=(first, second),
        currency="USD",
        starts_at=STARTS_AT,
        ends_at=ENDS_AT,
    )
    reverse = derive_journal_pnl_attribution_id(
        journal_entries=(second, first),
        currency="USD",
        starts_at=STARTS_AT,
        ends_at=ENDS_AT,
    )

    assert forward == reverse
    assert forward.startswith("pnl_")


def test_build_journal_pnl_attribution_rejects_duplicate_journal_ids() -> None:
    journal = _journal(
        journal_entry_id="journal_pnl_duplicate",
        lines=_pnl_lines(realized=Decimal("0.10"), fees=Decimal("0"), rebates=Decimal("0")),
    )

    with pytest.raises(PortfolioProjectionError, match="duplicate"):
        build_journal_pnl_attribution(
            journal_entries=(journal, journal),
            currency="USD",
            starts_at=STARTS_AT,
            ends_at=ENDS_AT,
        )


def test_build_journal_pnl_attribution_rejects_journals_outside_period() -> None:
    journal = _journal(
        occurred_at=ENDS_AT,
        created_at=ENDS_AT + timedelta(seconds=1),
        lines=_pnl_lines(realized=Decimal("0.10"), fees=Decimal("0"), rebates=Decimal("0")),
    )

    with pytest.raises(PortfolioProjectionError, match="within"):
        build_journal_pnl_attribution(
            journal_entries=(journal,),
            currency="USD",
            starts_at=STARTS_AT,
            ends_at=ENDS_AT,
        )


def test_build_journal_pnl_attribution_rejects_negative_fee_totals() -> None:
    journal = _journal(
        lines=(
            _line(ACCOUNT_FEES_PAID, "-0.01"),
            _line("fee_offset", "0.01"),
        )
    )

    with pytest.raises(PortfolioProjectionError, match="fees amount must be nonnegative"):
        build_journal_pnl_attribution(
            journal_entries=(journal,),
            currency="USD",
            starts_at=STARTS_AT,
            ends_at=ENDS_AT,
        )


def test_build_journal_pnl_attribution_rejects_mismatched_component_currency() -> None:
    journal = _journal(
        lines=_pnl_lines(realized=Decimal("0.10"), fees=Decimal("0"), rebates=Decimal("0"))
    )

    with pytest.raises(PortfolioProjectionError, match="slippage currency"):
        build_journal_pnl_attribution(
            journal_entries=(journal,),
            currency="USD",
            starts_at=STARTS_AT,
            ends_at=ENDS_AT,
            slippage=_money("0.01", currency="EUR"),
        )


def _journal(
    *,
    journal_entry_id: str = "journal_pnl_001",
    occurred_at: datetime = OCCURRED_AT,
    created_at: datetime = CREATED_AT,
    lines: tuple[JournalLine, ...],
) -> AccountingJournalEntry:
    return AccountingJournalEntry(
        journal_entry_id=journal_entry_id,
        occurred_at=occurred_at,
        source_event_id=EventId("evt_pnl_journal_001"),
        reference_type="fill",
        reference_id="fill_pnl_001",
        lines=lines,
        description="PnL attribution test journal.",
        created_at=created_at,
    )


def _pnl_lines(*, realized: Decimal, fees: Decimal, rebates: Decimal) -> tuple[JournalLine, ...]:
    component_lines = (
        _line(ACCOUNT_REALIZED_TRADING_PNL, -realized),
        _line(ACCOUNT_FEES_PAID, fees),
        _line(ACCOUNT_REBATES_RECEIVED, -rebates),
    )
    offset = -sum((line.amount for line in component_lines), start=Decimal("0"))
    return (*component_lines, _line("pnl_offset", offset))


def _line(account_code: str, amount: Decimal | str) -> JournalLine:
    return JournalLine(
        account_code=account_code,
        amount=amount,
        currency="USD",
        description=f"{account_code} line",
    )


def _money(amount: str, *, currency: str = "USD") -> Money:
    return Money(amount=Decimal(amount), currency=currency)
