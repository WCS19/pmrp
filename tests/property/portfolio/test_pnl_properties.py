"""Property tests for portfolio PnL attribution helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.portfolio import (
    ACCOUNT_FEES_PAID,
    ACCOUNT_REALIZED_TRADING_PNL,
    ACCOUNT_REBATES_RECEIVED,
    build_journal_pnl_attribution,
    derive_journal_pnl_attribution_id,
)
from pmrp.schemas.identifiers import EventId
from pmrp.schemas.numeric import Money
from pmrp.schemas.portfolio import AccountingJournalEntry, JournalLine

pytestmark = pytest.mark.property

STARTS_AT = datetime(2026, 9, 25, 14, 0, tzinfo=UTC)
ENDS_AT = datetime(2026, 9, 25, 15, 0, tzinfo=UTC)
OCCURRED_AT = datetime(2026, 9, 25, 14, 5, tzinfo=UTC)
CREATED_AT = datetime(2026, 9, 25, 14, 5, 1, tzinfo=UTC)

_SIGNED_MONEY = st.integers(min_value=-1_000_000, max_value=1_000_000).map(
    lambda cents: Decimal(cents) / Decimal("100")
)
_NONNEGATIVE_MONEY = st.integers(min_value=0, max_value=1_000_000).map(
    lambda cents: Decimal(cents) / Decimal("100")
)


@given(
    realized=_SIGNED_MONEY,
    unrealized=_SIGNED_MONEY,
    fees=_NONNEGATIVE_MONEY,
    rebates=_NONNEGATIVE_MONEY,
    slippage=_SIGNED_MONEY,
    settlement=_SIGNED_MONEY,
)
def test_build_journal_pnl_attribution_matches_component_sum(
    realized: Decimal,
    unrealized: Decimal,
    fees: Decimal,
    rebates: Decimal,
    slippage: Decimal,
    settlement: Decimal,
) -> None:
    journal = _journal(
        _pnl_lines(
            realized=realized,
            fees=fees,
            rebates=rebates,
        )
    )

    attribution = build_journal_pnl_attribution(
        journal_entries=(journal,),
        currency="USD",
        starts_at=STARTS_AT,
        ends_at=ENDS_AT,
        unrealized_pnl_change=_money(unrealized),
        slippage=_money(slippage),
        settlement_pnl=_money(settlement),
    )

    assert attribution.realized_trading_pnl.amount == realized
    assert attribution.unrealized_pnl_change.amount == unrealized
    assert attribution.fees.amount == fees
    assert attribution.rebates.amount == rebates
    assert attribution.slippage is not None
    assert attribution.slippage.amount == slippage
    assert attribution.settlement_pnl is not None
    assert attribution.settlement_pnl.amount == settlement
    assert (
        attribution.total_pnl.amount
        == realized + unrealized - fees + rebates + slippage + settlement
    )


@given(realized=_SIGNED_MONEY, fees=_NONNEGATIVE_MONEY, rebates=_NONNEGATIVE_MONEY)
def test_journal_pnl_attribution_id_is_independent_of_journal_order(
    realized: Decimal,
    fees: Decimal,
    rebates: Decimal,
) -> None:
    first = _journal(
        _pnl_lines(realized=realized, fees=fees, rebates=rebates),
        journal_entry_id="journal_property_pnl_first",
    )
    second = _journal(
        _pnl_lines(realized=-realized, fees=Decimal("0"), rebates=Decimal("0")),
        journal_entry_id="journal_property_pnl_second",
    )

    assert derive_journal_pnl_attribution_id(
        journal_entries=(first, second),
        currency="USD",
        starts_at=STARTS_AT,
        ends_at=ENDS_AT,
    ) == derive_journal_pnl_attribution_id(
        journal_entries=(second, first),
        currency="USD",
        starts_at=STARTS_AT,
        ends_at=ENDS_AT,
    )


def _journal(
    lines: tuple[JournalLine, ...],
    *,
    journal_entry_id: str = "journal_property_pnl_001",
) -> AccountingJournalEntry:
    return AccountingJournalEntry(
        journal_entry_id=journal_entry_id,
        occurred_at=OCCURRED_AT,
        source_event_id=EventId("evt_property_pnl_journal"),
        reference_type="fill",
        reference_id="fill_property_pnl",
        lines=lines,
        description="Property PnL attribution journal.",
        created_at=CREATED_AT,
    )


def _pnl_lines(*, realized: Decimal, fees: Decimal, rebates: Decimal) -> tuple[JournalLine, ...]:
    component_lines = (
        _line(ACCOUNT_REALIZED_TRADING_PNL, -realized),
        _line(ACCOUNT_FEES_PAID, fees),
        _line(ACCOUNT_REBATES_RECEIVED, -rebates),
    )
    offset = -sum((line.amount for line in component_lines), start=Decimal("0"))
    return (*component_lines, _line("pnl_offset", offset))


def _line(account_code: str, amount: Decimal) -> JournalLine:
    return JournalLine(
        account_code=account_code,
        amount=amount,
        currency="USD",
        description=f"{account_code} line",
    )


def _money(amount: Decimal) -> Money:
    return Money(amount=amount, currency="USD")
