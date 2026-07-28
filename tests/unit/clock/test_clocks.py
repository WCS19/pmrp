from datetime import UTC, datetime, timedelta

import pytest

from pmrp.clock import AdvancingTestClock, Clock, FrozenClock, ReplayClock, SystemClock

pytestmark = pytest.mark.unit


def _instant() -> datetime:
    return datetime(2026, 7, 28, 19, 0, tzinfo=UTC)


def test_clock_implementations_satisfy_protocol() -> None:
    assert isinstance(SystemClock(), Clock)
    assert isinstance(FrozenClock(_instant()), Clock)
    assert isinstance(AdvancingTestClock(_instant()), Clock)
    assert isinstance(
        ReplayClock(
            starts_at=_instant(),
            ends_at=_instant() + timedelta(hours=1),
        ),
        Clock,
    )


def test_system_clock_now_returns_timezone_aware_utc() -> None:
    current_time = SystemClock().now()

    assert current_time.tzinfo is UTC
    assert current_time.utcoffset() == timedelta(0)


async def test_system_clock_rejects_negative_sleep_duration() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        await SystemClock().sleep(timedelta(microseconds=-1))


def test_frozen_clock_normalizes_input_to_utc() -> None:
    clock = FrozenClock(datetime.fromisoformat("2026-07-28T13:00:00-06:00"))

    assert clock.now() == _instant()


async def test_frozen_clock_sleep_does_not_advance_time() -> None:
    clock = FrozenClock(_instant())

    await clock.sleep(timedelta(hours=1))

    assert clock.now() == _instant()


def test_frozen_clock_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        FrozenClock(datetime.fromisoformat("2026-07-28T19:00:00"))


def test_advancing_test_clock_advance_moves_virtual_time_exactly() -> None:
    clock = AdvancingTestClock(_instant())

    assert clock.advance(timedelta(seconds=90)) == _instant() + timedelta(seconds=90)
    assert clock.now() == _instant() + timedelta(seconds=90)


async def test_advancing_test_clock_sleep_advances_virtual_time_exactly() -> None:
    clock = AdvancingTestClock(_instant())

    await clock.sleep(timedelta(milliseconds=250))

    assert clock.now() == _instant() + timedelta(milliseconds=250)


def test_advancing_test_clock_rejects_negative_advance() -> None:
    clock = AdvancingTestClock(_instant())

    with pytest.raises(ValueError, match="must not be negative"):
        clock.advance(timedelta(seconds=-1))


def test_advancing_test_clock_set_normalizes_to_utc() -> None:
    clock = AdvancingTestClock(_instant())

    assert clock.set(datetime.fromisoformat("2026-07-28T13:30:00-06:00")) == _instant() + timedelta(
        minutes=30
    )


def test_replay_clock_defaults_to_window_start() -> None:
    clock = ReplayClock(starts_at=_instant(), ends_at=_instant() + timedelta(hours=1))

    assert clock.now() == _instant()
    assert clock.starts_at == _instant()
    assert clock.ends_at == _instant() + timedelta(hours=1)


def test_replay_clock_rejects_invalid_window() -> None:
    with pytest.raises(ValueError, match="must not precede"):
        ReplayClock(starts_at=_instant(), ends_at=_instant() - timedelta(microseconds=1))


def test_replay_clock_rejects_initial_time_outside_window() -> None:
    with pytest.raises(ValueError, match="within the replay window"):
        ReplayClock(
            starts_at=_instant(),
            ends_at=_instant() + timedelta(hours=1),
            current_time=_instant() + timedelta(hours=2),
        )


def test_replay_clock_advance_to_allows_seek_within_window() -> None:
    clock = ReplayClock(starts_at=_instant(), ends_at=_instant() + timedelta(hours=1))

    assert clock.advance_to(_instant() + timedelta(minutes=30)) == _instant() + timedelta(
        minutes=30
    )
    assert clock.advance_to(_instant() + timedelta(minutes=15)) == _instant() + timedelta(
        minutes=15
    )


def test_replay_clock_rejects_advance_beyond_window() -> None:
    clock = ReplayClock(starts_at=_instant(), ends_at=_instant() + timedelta(hours=1))

    with pytest.raises(ValueError, match="within the replay window"):
        clock.advance(timedelta(hours=2))


async def test_replay_clock_sleep_advances_virtual_time() -> None:
    clock = ReplayClock(starts_at=_instant(), ends_at=_instant() + timedelta(hours=1))

    await clock.sleep(timedelta(minutes=5))

    assert clock.now() == _instant() + timedelta(minutes=5)


def test_replay_clock_reset_returns_to_window_start() -> None:
    clock = ReplayClock(
        starts_at=_instant(),
        ends_at=_instant() + timedelta(hours=1),
        current_time=_instant() + timedelta(minutes=30),
    )

    assert clock.reset() == _instant()
