# Issue: DST wall-clock drift, spring-forward gap handling, and elapsed duration errors in `chronoshift`

## Description
`chronoshift` calculates timezone-aware maintenance windows and real elapsed SLA durations using `zoneinfo`. Three bugs occur across Daylight Saving Time transitions (e.g., `America/New_York`):

1. **`generate_daily_occurrences` shifts wall-clock hour after DST transition**:
   `generate_daily_occurrences(start_date, days, hour, minute, tz_name)` converts the initial timestamp to UTC and adds `timedelta(days=i)` in UTC before converting back to `ZoneInfo(tz_name)`. Across the spring-forward transition (`2026-03-08`), a `09:00 America/New_York` schedule shifts to `10:00 EDT`! Each day's occurrence must be anchored to `(hour, minute)` in the target timezone's local wall clock.
2. **`resolve_wall_time` fails to detect nonexistent spring-forward times**:
   During spring-forward (`2026-03-08` in `America/New_York`, where `02:00` jumps to `03:00`), `02:30` does not exist. Python's `datetime(..., tzinfo=tz)` does not raise automatically; a time is nonexistent if converting `dt.astimezone(UTC).astimezone(tz)` produces a different local wall time `(hour, minute)` or offset than `dt`.
   - When `nonexistent_policy == "raise"`, `resolve_wall_time` must raise `NonExistentTimeError`.
   - When `nonexistent_policy == "shift_forward"`, it must advance to the valid post-transition instant (`dt.astimezone(UTC).astimezone(tz)` or the start of the new hour `03:00 EDT` — specifically, shifting forward by the gap duration, which `dt.replace(fold=0).astimezone(UTC).astimezone(tz)` gives in Python's `zoneinfo`, or shifting to the exact post-transition minute `03:30 EDT` / `03:00 EDT`: let's standardize on `dt.replace(fold=0).astimezone(UTC).astimezone(tz)` so `02:30` shifts forward by the 1-hour DST gap to `03:30 EDT`!).
3. **`real_elapsed_seconds(start_dt, end_dt)` strips tzinfo instead of comparing in UTC**:
   Stripping `tzinfo` treats the 23-hour spring-forward day as 24 hours and the 25-hour fall-back day as 24 hours. It must convert both aware datetimes to `UTC` before subtracting.

## Expected Behavior
- `generate_daily_occurrences` preserves local wall-clock `(hour, minute)` across DST transitions.
- `resolve_wall_time` detects nonexistent spring-forward wall times, raising `NonExistentTimeError` on `"raise"` and shifting forward by the DST gap (`dt.replace(fold=0).astimezone(UTC).astimezone(tz)`) on `"shift_forward"`, and respects `fold` (`0` vs `1`) for ambiguous fall-back times.
- `real_elapsed_seconds` returns exact UTC elapsed seconds between two timezone-aware datetimes.
