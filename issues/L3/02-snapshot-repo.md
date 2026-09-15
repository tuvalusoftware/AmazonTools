# 2. `SnapshotRepo` — month-scoped query + distinct-ASIN listing

## Where

`utils/Repo_Snapshot.py` — add two read-only methods to the existing
`SnapshotRepo` class, next to `load_daily_snapshots`.

## `load_daily_snapshots_for_month`

The monthly job (see [04](./04-monthly-job.md)) needs exactly one month's
worth of day rows per ASIN — not the full history that
`load_daily_snapshots(asin, days=0)` would return, and not a day-count
window (which can't express "give me July 2026" once August has started).

```python
def load_daily_snapshots_for_month(
    self, asin: str, year: int, month: int
) -> list[DailySnapshotRow]:
    """Return date-grouped BSR rows for *asin* restricted to one calendar month.

    Same per-day aggregation as ``load_daily_snapshots`` (best rank, highest
    price per day), oldest-first, but scoped to ``year``/``month`` instead of
    a rolling day-count window.
    """
```

SQL — reuse the same `GROUP BY DATE(scraped_at)` shape, filtered with
SQLite's `strftime`:

```sql
SELECT DATE(scraped_at) AS date,
       MIN(rank)        AS rank,
       MAX(price)       AS price
FROM   bsr_snapshots
WHERE  asin = ?
  AND  strftime('%Y', scraped_at) = ?
  AND  strftime('%m', scraped_at) = ?
GROUP  BY DATE(scraped_at)
ORDER  BY DATE(scraped_at) ASC
```

Parameters: `(asin, f"{year:04d}", f"{month:02d}")` — `strftime('%m', ...)`
is zero-padded, so `month` must be formatted the same way.

Same UTC-boundary caveat already noted for `load_daily_snapshots` applies
here unchanged (`DATE(scraped_at)`/`strftime` both operate on the UTC
`scraped_at` string written by `jobs/scrape_bsr.py`) — out of scope to fix
as part of this issue.

## `list_asins_that_have_data`

The monthly job needs "every ASIN that ever has a snapshot row", which is
broader than `BookRepo.load_active_books()` (active-only) — see scope
decision in `main.md`.

```python
def list_asins_that_have_data(self) -> list[str]:
    """Return every distinct ASIN that has at least one row in bsr_snapshots."""
```

```sql
SELECT DISTINCT asin FROM bsr_snapshots
```

## Test coverage

Add to `tests/test_snapshot_repo.py`, mirroring the existing
`load_daily_snapshots` tests:

- `load_daily_snapshots_for_month` returns only rows within the requested
  month when snapshots span multiple months (e.g. seed late-July +
  all-August + early-September rows, query August, assert exactly the
  August dates come back, in order).
- `load_daily_snapshots_for_month` returns `[]` for a month with no data
  (not `None` — matches the "empty list when no rows exist" convention
  already documented on `load_daily_snapshots`).
- `list_asins_that_have_data` returns distinct ASINs (seed duplicate-ASIN rows,
  assert each ASIN appears once) including one that only exists in
  `bsr_snapshots` with no corresponding *active* `tracked_books` row (i.e.
  don't join through `tracked_books` at all).
