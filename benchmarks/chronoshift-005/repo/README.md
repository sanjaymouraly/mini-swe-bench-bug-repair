# `chronoshift` — Fix DST wall-clock drift, nonexistent spring-forward times, and UTC elapsed calculation

DailyWindowScheduler shifts wall-clock hours across DST transitions by adding UTC timedeltas, fails to detect nonexistent spring-forward gap times, and miscomputes real elapsed seconds across offset changes.

## Running Tests

```bash
PYTHONPATH=src pytest -q
```
