from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.clock import AdvancingTestClock, ReplayClock

pytestmark = pytest.mark.property

_START = datetime(2026, 7, 28, 19, 0, tzinfo=UTC)


@given(microseconds=st.integers(min_value=0, max_value=86_400_000_000))
def test_advancing_test_clock_advances_by_exact_generated_duration(microseconds: int) -> None:
    duration = timedelta(microseconds=microseconds)
    clock = AdvancingTestClock(_START)

    assert clock.advance(duration) == _START + duration
    assert clock.now() == _START + duration


@given(
    window_seconds=st.integers(min_value=0, max_value=86_400),
    offset_seconds=st.integers(min_value=0, max_value=86_400),
)
def test_replay_clock_accepts_generated_times_within_window(
    window_seconds: int,
    offset_seconds: int,
) -> None:
    bounded_offset_seconds = min(offset_seconds, window_seconds)
    ends_at = _START + timedelta(seconds=window_seconds)
    current_time = _START + timedelta(seconds=bounded_offset_seconds)

    clock = ReplayClock(starts_at=_START, ends_at=ends_at, current_time=current_time)

    assert clock.now() == current_time
    assert clock.advance_to(_START) == _START
    assert clock.advance_to(ends_at) == ends_at


@given(window_seconds=st.integers(min_value=0, max_value=86_400))
def test_replay_clock_rejects_generated_times_after_window(window_seconds: int) -> None:
    clock = ReplayClock(
        starts_at=_START,
        ends_at=_START + timedelta(seconds=window_seconds),
    )

    with pytest.raises(ValueError, match="within the replay window"):
        clock.advance_to(_START + timedelta(seconds=window_seconds, microseconds=1))
