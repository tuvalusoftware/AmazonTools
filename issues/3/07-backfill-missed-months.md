# 7. Self-healing backfill for missed monthly runs

## Problem

[4](./04-monthly-job.md)'s job only ever computes *the single calendar
month right before today*. If the app is down, crashed, or mid-redeploy at
the moment `MONTHLY_SUMMARY_CRON` fires (`5 0 1 * *`), that month is never
computed — the next run a month later only looks at the *new* previous
month, permanently skipping the missed one. The skipped month then falls
back to live aggregation forever (correct numbers, but defeats the whole
point of precomputing).

## Change

Replace "compute last month" with "compute every completed month that
doesn't have a row yet, from the ASIN's earliest snapshot up to last
month." Already-stored months are skipped cheaply via
`MonthlySummaryRepo.get()`, so a normal run (nothing missed) still does
exactly one month of work per ASIN — this only changes behavior when
there's a gap.

## Where

`utils/Repo_Snapshot.py` — add one method next to
`load_daily_snapshots_for_month`:

```python
def get_data_month_range(self, asin: str) -> tuple[int, int, int, int] | None:
    """Return (start_year, start_month, end_year, end_month) spanning every
    calendar month that has at least one bsr_snapshots row for *asin*,
    inclusive on both ends. None if *asin* has no rows at all."""
```

```sql
SELECT MIN(DATE(scraped_at)) AS first_date, MAX(DATE(scraped_at)) AS last_date
FROM   bsr_snapshots
WHERE  asin = ?
```

Derive `(start_year, start_month)` / `(end_year, end_month)` from the two
returned dates in Python (`date.fromisoformat(...).year/.month`) — no need
for a second query.

## `jobs/monthly_summary.py`

Replace the single-month loop body in `run()`:

```python
def _months_between(start: tuple[int, int], end: tuple[int, int]) -> list[tuple[int, int]]:
    """Inclusive list of (year, month) tuples from start to end, both inclusive."""
    months = []
    y, m = start
    while (y, m) <= end:
        months.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return months


def run() -> None:
    last_complete = _target_month()  # unchanged: month before today, per settings.TIMEZONE

    snapshot_repo = SnapshotRepo()
    book_repo = BookRepo()
    summary_repo = MonthlySummaryRepo()

    asins = snapshot_repo.list_asins_that_have_data()
    computed = 0
    skipped_existing = 0

    for asin in asins:
        data_range = snapshot_repo.get_data_month_range(asin)
        if data_range is None:
            continue
        start_y, start_m, end_y, end_m = data_range
        end = min((end_y, end_m), last_complete)  # never touch the in-progress current month

        for year, month in _months_between((start_y, start_m), end):
            if summary_repo.get(asin, year, month) is not None:
                skipped_existing += 1
                continue  # already computed — normal case for every month but the newest gap

            rows = snapshot_repo.load_daily_snapshots_for_month(asin, year, month)
            if not rows:
                continue  # ASIN had no data that particular month (e.g. added mid-range)

            profit_pct = ...  # same resolution as today, via BookRepo.find_book_by_asin
            total_units, total_profit, days_with_data = aggregate_month(rows, profit_pct)
            summary_repo.save(asin, year, month, total_units, total_profit, days_with_data)
            computed += 1

    log.info(
        "Monthly summary: %d month(s) computed, %d already up to date",
        computed, skipped_existing,
    )
```

`min((end_y, end_m), last_complete)` guards the edge case where
`bsr_snapshots` somehow has a row dated in the current (in-progress) month
— tuple comparison works directly since `(year, month)` sorts
lexicographically.

`_target_month()` (added in [4](./04-monthly-job.md)) is reused unchanged
as the upper bound; nothing about its own logic changes.

## Cost note

`MonthlySummaryRepo.get()` is one indexed lookup per already-computed
month — negligible even for an ASIN with a few years of history. This
runs once a month, not on a hot path, so no batching/optimization needed.

## Test coverage

Extend `tests/test_monthly_summary_job.py`:

- ASIN with 3 completed months of data and **no** precomputed rows at all
  (simulates first run after a 3-month outage) → `save()` is called once
  per month, all 3.
- ASIN with the oldest 2 of 3 completed months already precomputed
  (simulates the normal steady-state case) → `save()` is called only for
  the 1 missing month; `MonthlySummaryRepo.get()` for the other 2 is what
  causes the skip (assert `save` call count == 1, not that `get` was
  called — implementation detail).
- ASIN with a data row inside the current in-progress month → that month
  is never included in the walk, even though `get_data_month_range` would
  otherwise include it (assert `save` is never called with the current
  `(year, month)`).
- `get_data_month_range` returns `None` for an ASIN with no `bsr_snapshots`
  rows at all (shouldn't be reachable via `list_asins_that_have_data`
  today, but keep the method's own contract honest — add directly to
  `tests/test_snapshot_repo.py`).
