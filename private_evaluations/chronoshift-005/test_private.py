"""Private DST fall-back fold and 25-hour day tests for chronoshift-005."""

from datetime import date
from chronoshift import DailyWindowScheduler, real_elapsed_seconds, resolve_wall_time


def test_fall_back_25_hour_day_and_fold_disambiguation():
    # America/New_York falls back on 2026-11-01 at 02:00 -> 01:00
    sched = DailyWindowScheduler("America/New_York")
    occ = sched.generate_daily_occurrences(date(2026, 10, 31), days=3, hour=9, minute=0)
    assert [(d.hour, d.minute) for d in occ] == [(9, 0), (9, 0), (9, 0)]
    # Between Oct 31 09:00 EDT and Nov 1 09:00 EST is 25 hours (90000s)
    assert real_elapsed_seconds(occ[0], occ[1]) == 25 * 3600

    # Ambiguous time 01:30 on 2026-11-01 has fold=0 (EDT) and fold=1 (EST), 3600s apart
    first_130 = resolve_wall_time(date(2026, 11, 1), 1, 30, "America/New_York", fold=0)
    second_130 = resolve_wall_time(date(2026, 11, 1), 1, 30, "America/New_York", fold=1)
    assert real_elapsed_seconds(first_130, second_130) == 3600.0
