"""Pre-existing preservation tests for chronoshift."""

from datetime import UTC, date, datetime
import pytest
from chronoshift import DailyWindowScheduler, real_elapsed_seconds, resolve_wall_time


def test_utc_daily_schedule():
    sched = DailyWindowScheduler("UTC")
    occ = sched.generate_daily_occurrences(date(2026, 1, 10), days=3, hour=14, minute=30)
    assert len(occ) == 3
    assert [d.hour for d in occ] == [14, 14, 14]
    assert [d.day for d in occ] == [10, 11, 12]


def test_real_elapsed_seconds_rejects_naive_datetime():
    aware = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    naive = datetime(2026, 1, 1, 13, 0)
    with pytest.raises(ValueError):
        real_elapsed_seconds(aware, naive)


def test_resolve_normal_wall_time():
    dt = resolve_wall_time(date(2026, 6, 15), 10, 15, "America/New_York")
    assert dt.hour == 10
    assert dt.minute == 15
