"""Issue-specific FAIL_TO_PASS tests for chronoshift-005."""

from datetime import date
import pytest
from chronoshift import (
    DailyWindowScheduler,
    NonExistentTimeError,
    real_elapsed_seconds,
    resolve_wall_time,
)


def test_daily_schedule_preserves_wall_clock_across_spring_forward_dst():
    # America/New_York springs forward on 2026-03-08
    sched = DailyWindowScheduler("America/New_York")
    occ = sched.generate_daily_occurrences(date(2026, 3, 7), days=3, hour=9, minute=0)
    assert [(d.hour, d.minute) for d in occ] == [(9, 0), (9, 0), (9, 0)]
    # Real elapsed time between 09:00 EST on Mar 7 and 09:00 EDT on Mar 8 is 23 hours (82800s)
    assert real_elapsed_seconds(occ[0], occ[1]) == 23 * 3600


def test_nonexistent_spring_forward_time_raise_and_shift():
    # 2026-03-08 02:30 does not exist in America/New_York
    with pytest.raises(NonExistentTimeError):
        resolve_wall_time(
            date(2026, 3, 8), 2, 30, "America/New_York", nonexistent_policy="raise"
        )

    shifted = resolve_wall_time(
        date(2026, 3, 8), 2, 30, "America/New_York", nonexistent_policy="shift_forward"
    )
    assert (shifted.hour, shifted.minute) == (3, 30)
