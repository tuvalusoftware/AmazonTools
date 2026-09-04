# 7. Self-healing backfill, triggered from the daily scrape

## Problem

[4](./04-monthly-job.md)'s job only ever computes *the single calendar
month right before today*, and only runs once a month
(`MONTHLY_SUMMARY_CRON`, `5 0 1 * *`). If the app is down, crashed, or
mid-redeploy at the moment that cron fires, the just-completed month is
never computed — the next run a month later only looks at the *new*
previous month, permanently skipping the missed one. The skipped month
then falls back to live aggregation forever (correct numbers, but defeats
the point of precomputing).

## Change

Two parts:

1. **Shared self-heal function** — `jobs/monthly_summary.py` gets a new
   per-ASIN entry point, `sync_missing_months(asin)`, that walks every
   completed calendar month between an ASIN's earliest snapshot and last
   month, computing and saving any month that doesn't have a stored row
   yet. Already-stored months are skipped cheaply via
   `MonthlySummaryRepo.get()`.
2. **New trigger: the daily scrape itself.** `jobs/scrape_bsr.py` calls
   `sync_missing_months(asin)` for each ASIN right after successfully
   saving that day's snapshot — not just once a month from the cron. This
   means a gap gets healed the same day the scraper next runs
   successfully, instead of waiting up to a month for
   `MONTHLY_SUMMARY_CRON` to fire again, and it stops depending on the
   monthly cron ever firing correctly at all for actively-tracked ASINs.

The monthly cron job (`run()`) is kept, unchanged in schedule, as a safety
net — it still calls `sync_missing_months` for every ASIN with any
snapshot history, active or not. This matters because `scrape_bsr.run()`
only iterates `BookRepo().load_active_books()`, so unsubscribed ASINs
never go through the daily trigger; the monthly cron remains their only
path to a backfilled summary.

## Where

### `utils/Repo_Snapshot.py`

Add one method next to `load_daily_snapshots_for_month`:

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

### `jobs/monthly_summary.py`

```python
def _months_between(start: tuple[int, int], end: tuple[int, int]) -> list[tuple[int, int]]:
    """Inclusive list of (year, month) tuples from start to end, both inclusive."""
    months = []
    y, m = start
    while (y, m) <= end:
        months.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return months


def _resolve_profit_pct(book_repo: BookRepo, asin: str) -> float:
    book_row = book_repo.find_book_by_asin(asin)
    if book_row is None:
        return _DEFAULT_PROFIT_PCT
    raw_pct = book_row.get("profit_pct")
    return float(raw_pct) if isinstance(raw_pct, (int, float)) and raw_pct else _DEFAULT_PROFIT_PCT


def sync_missing_months(
    asin: str,
    *,
    snapshot_repo: SnapshotRepo | None = None,
    book_repo: BookRepo | None = None,
    summary_repo: MonthlySummaryRepo | None = None,
) -> int:
    """Compute and store every completed calendar month missing a summary
    row for *asin*, from its earliest snapshot up to last month.

    Cheap no-op when already up to date: a normal call (nothing missed)
    does exactly one `get_data_month_range` + a handful of indexed
    `MonthlySummaryRepo.get()` lookups, no `save()`. Safe to call once per
    ASIN per scrape, every day.

    Returns the number of months computed (0 if nothing was missing).
    """
    snapshot_repo = snapshot_repo or SnapshotRepo()
    book_repo = book_repo or BookRepo()
    summary_repo = summary_repo or MonthlySummaryRepo()

    data_range = snapshot_repo.get_data_month_range(asin)
    if data_range is None:
        return 0

    start_y, start_m, end_y, end_m = data_range
    last_complete = _target_month()
    end = min((end_y, end_m), last_complete)  # never touch the in-progress current month

    computed = 0
    for year, month in _months_between((start_y, start_m), end):
        if summary_repo.get(asin, year, month) is not None:
            continue  # already computed — normal case for every month but a genuine gap

        rows = snapshot_repo.load_daily_snapshots_for_month(asin, year, month)
        if not rows:
            continue  # ASIN had no data that particular month (e.g. added mid-range)

        profit_pct = _resolve_profit_pct(book_repo, asin)
        total_units, total_profit, days_with_data = aggregate_month(rows, profit_pct)
        summary_repo.save(asin, year, month, total_units, total_profit, days_with_data)
        computed += 1

    return computed


def run() -> None:
    """Monthly cron entry point — self-heals every ASIN with any snapshot
    history (active or not). Complements the per-ASIN call from
    jobs/scrape_bsr.py, which only covers active ASINs but runs daily."""
    snapshot_repo = SnapshotRepo()
    book_repo = BookRepo()
    summary_repo = MonthlySummaryRepo()

    asins = snapshot_repo.list_asins_that_have_data()
    total_computed = 0
    for asin in asins:
        total_computed += sync_missing_months(
            asin, snapshot_repo=snapshot_repo, book_repo=book_repo, summary_repo=summary_repo,
        )

    log.info(
        "Monthly summary cron: %d month(s) computed across %d ASIN(s)",
        total_computed, len(asins),
    )
```

`min((end_y, end_m), last_complete)` guards the edge case where
`bsr_snapshots` somehow has a row dated in the current (in-progress)
month — tuple comparison works directly since `(year, month)` sorts
lexicographically.

`_target_month()` (added in [4](./04-monthly-job.md)) is reused unchanged
as the upper bound.

### `jobs/scrape_bsr.py`

In `run()`, right after a successful save for an ASIN:

```python
if ranks:
    saved = repo.save_bsr_snapshots(ranks)
    total_saved += saved

    try:
        computed = sync_missing_months(asin)
        if computed:
            log.info("ASIN %s — backfilled %d missing monthly summary month(s)", asin, computed)
    except Exception as exc:
        log.warning("ASIN %s — monthly summary sync failed (will retry next scrape): %s", asin, exc)
else:
    log.warning("ASIN %s — no BSR data found", asin)
```

Import `sync_missing_months` from `jobs.monthly_summary` at module level,
same as any other cross-job import in this codebase.

The `try/except` is required: a failure computing/saving a monthly
summary must never abort the scrape loop or lose that day's BSR snapshot,
which is the job's primary purpose. Errors are logged and self-heal again
on the next successful scrape for that ASIN (or the next monthly cron
run), since nothing was marked as done.

Only called when `ranks` is non-empty (i.e. the scrape actually produced
a snapshot to save) — if the scrape failed for that ASIN today, there's
no new data and no reason to redo the (cheap but non-zero) month walk;
the next successful scrape or the monthly cron will still catch any real
gap.

## Cost note

`MonthlySummaryRepo.get()` is one indexed lookup per already-computed
month — negligible even for an ASIN with a few years of history.
Previously this walk only ran once a month (in the cron); now it also
runs once per ASIN per day (in `scrape_bsr`), which is still O(months of
history) indexed lookups per ASIN per day, not O(days) — a book tracked
for 2 years adds ~24 cheap `get()` calls to each day's scrape, not 730.

## Test coverage

`tests/test_monthly_summary_job.py` needs updating for the new shape —
`run()` no longer directly aggregates a single target month per ASIN, it
delegates to `sync_missing_months`. Restructure around testing
`sync_missing_months` directly and `run()` as a thin loop over it:

- `sync_missing_months`, ASIN with 3 completed months of data and **no**
  precomputed rows at all (simulates first run after a 3-month outage) →
  `save()` is called once per month, all 3; return value is `3`.
- `sync_missing_months`, ASIN with the oldest 2 of 3 completed months
  already precomputed (steady-state case) → `save()` is called only for
  the 1 missing month; return value is `1`.
- `sync_missing_months`, ASIN with a data row inside the current
  in-progress month → that month is never included in the walk, even
  though `get_data_month_range` would otherwise include it (assert `save`
  is never called with the current `(year, month)`).
- `sync_missing_months`, ASIN fully up to date → `save()` not called,
  return value `0`.
- `get_data_month_range` returns `None` for an ASIN with no
  `bsr_snapshots` rows at all → `sync_missing_months` returns `0` without
  touching `MonthlySummaryRepo` (add directly to
  `tests/test_snapshot_repo.py` for the repo method itself).
- `run()` still covers all ASINs from `list_asins_that_have_data()`
  (active or not) and sums `sync_missing_months`' return values into its
  log line — a thin test mocking `sync_missing_months` itself is enough,
  no need to re-verify aggregation math at this layer.
- Unsubscribed-mid-month / no-`tracked_books`-row profit_pct fallback
  cases move from testing `run()` to testing `sync_missing_months`
  directly (same scenarios, same expected behavior, just at the new call
  site).

New coverage in `tests/test_scrape_bsr.py`:

- After a successful save for an ASIN, `run()` calls
  `jobs.monthly_summary.sync_missing_months(asin)` exactly once.
- `sync_missing_months` raising does **not** abort the loop — the next
  ASIN is still scraped and `total_saved` still reflects prior
  successful saves; the exception is logged, not re-raised.
- When `ranks` is empty for an ASIN (no BSR data found), `sync_missing_months`
  is **not** called for it.
