# 4. `jobs/monthly_summary.py` — the new monthly cron job

## Where

New file `jobs/monthly_summary.py`, same shape as `jobs/email_digest.py`
and `jobs/scrape_bsr.py` (module-level `run()` entry point, `get_logger`
from `utils.logger`).

## Shared aggregation helper (avoid duplicating the formula)

`Helper_Pdf_Metrics.compute()` currently inlines the per-day → per-month
aggregation (lines 94-105 today: accumulate `total_units`, `total_profit`,
`days_with_data` per `(year, month)` bucket using
`Formula.estimated_units_per_day` / `Formula.daily_profit`). This job needs
the *exact same* aggregation for one month's rows, and
`Helper_Pdf_Metrics` still needs it as a fallback for months with no
precomputed row (see [06](./06-metrics-integration.md)) — so extract it
once rather than duplicating the formula in two places.

Add a small module-level function to `reports/Helper_Pdf_Metrics.py` (or a
new `reports/Helper_Monthly_Aggregate.py` if that file is getting crowded —
judgment call at implementation time, keep it small either way):

```python
def aggregate_month(
    rows: list[DailySnapshotRow], profit_pct: float
) -> tuple[int, float, int]:
    """Aggregate one month's daily snapshot rows into (total_units, total_profit, days_with_data).

    Same units/profit formula as the daily series: Formula.estimated_units_per_day
    and Formula.daily_profit per row, summed.
    """
```

Both `Helper_Pdf_Metrics.compute()`'s live-fallback path and
`jobs/monthly_summary.py` call this instead of re-deriving the sums
independently.

## Job logic

```python
def run() -> None:
    """Compute and persist the previous calendar month's profit summary
    for every ASIN that has any snapshot history (active or not)."""
```

1. Determine the target month: the calendar month *before* today
   (`date.today()`), computed against `settings.TIMEZONE` — reuse whatever
   "today in configured timezone" helper `jobs/scrape_bsr.py` or
   `jobs/email_digest.py` already uses, if one exists; otherwise
   `datetime.now(ZoneInfo(settings.TIMEZONE)).date()` then roll back one
   month (`year, month = (d.year, d.month - 1) if d.month > 1 else (d.year - 1, 12)`).
2. `asins = SnapshotRepo().list_asins_that_have_data()`.
3. For each `asin`:
   - `rows = SnapshotRepo().load_daily_snapshots_for_month(asin, year, month)`.
   - If `rows` is empty, skip (no data at all for that ASIN that month —
     don't write a zeroed-out row; `MonthlySummaryRepo.get()` returning
     `None` and the live-fallback path in `Helper_Pdf_Metrics` already
     handle "no data" correctly without needing a stored placeholder).
   - Resolve `profit_pct` the same way `Helper_Pdf_Loader.load()` does
     today (lines 61-67: look up the book in `BookRepo().load_active_books()`
     by ASIN; **but** per the scope decision this job must also cover
     unsubscribed ASINs, which `load_active_books()` excludes — so this
     needs a lookup that finds the book row regardless of `active`, e.g. a
     new `BookRepo` method or a raw query; fall back to the same
     `_DEFAULT_PROFIT_PCT = 70.0` used in `Helper_Pdf_Loader` when no
     `tracked_books` row exists at all).
   - `total_units, total_profit, days_with_data = aggregate_month(rows, profit_pct)`.
   - `MonthlySummaryRepo().save(asin, year, month, total_units, total_profit, days_with_data)`.
4. Log a summary line (`log.info("Monthly summary computed for %d ASIN(s) — %s %04d",
   count, month, year)`), matching the logging style of the other jobs.

## New `BookRepo` lookup needed

`Helper_Pdf_Loader.load()` resolves `profit_pct` via
`self._repo.load_active_books()`, which only returns `active=1` rows —
insufficient here since this job must price unsubscribed ASINs too. Add:

```python
def find_book_by_asin(self, asin: str) -> dict[str, object] | None:
    """Return any tracked_books row for *asin* (active or not), or None."""
```

```sql
SELECT * FROM tracked_books WHERE asin = ? ORDER BY active DESC LIMIT 1
```

(`ORDER BY active DESC` — prefer an active row if the same ASIN is tracked
by multiple emails with mixed active status; any one row's `profit_pct` is
an acceptable approximation here since profit_pct is nominally a
per-book, not truly per-subscription, property — same assumption
`Helper_Pdf_Loader` already makes today.)

## Test coverage

New `tests/test_monthly_summary_job.py`, mirroring
`tests/test_pdf_service.py`'s mocking style (patch `SnapshotRepo`,
`BookRepo`, `MonthlySummaryRepo` at the `jobs.monthly_summary` import
site):

- Given two ASINs with data in the target month, `run()` calls
  `MonthlySummaryRepo.save` once per ASIN with the correct aggregated
  numbers (verify against a hand-computed expected total for a small
  fixed rank/price series).
- An ASIN with **no** rows in the target month is skipped — `save` is not
  called for it.
- An ASIN whose only `tracked_books` row is `active=0` still gets a
  summary row computed and saved (covers the "unsubscribed ASINs still
  counted" scope decision).
- An ASIN with no `tracked_books` row at all falls back to the default
  70% profit_pct rather than raising.
- Calling `run()` twice for the same month is idempotent at the DB layer
  (delegates to `MonthlySummaryRepo.save`'s upsert — covered directly in
  [03](./03-monthly-summary-repo.md)'s tests, just confirm the job doesn't
  add its own accidental duplication, e.g. no manual `INSERT`).
