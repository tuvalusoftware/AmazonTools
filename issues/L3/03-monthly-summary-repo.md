# 3. `MonthlySummaryRepo` — read/write access to `book_monthly_summary`

## Where

New file `utils/Repo_MonthlySummary.py`, same shape as
`utils/Repo_Snapshot.py::SnapshotRepo` (thread-safe, own connection per
call, `settings.DB_PATH` default). This is a distinct concern from
`BookRepo` (tracked books) and `SnapshotRepo` (raw snapshot reads), so it
gets its own repo class per the "no god object" convention already used in
this codebase — and per `CLAUDE.md`, callers must instantiate and call
directly (`MonthlySummaryRepo().save(...)`), never through a module-level
wrapper function.

## Types

```python
class MonthlySummary(TypedDict):
    asin: str
    year: int
    month: int
    total_units: int
    total_profit: float
    days_with_data: int
```

Owned here (producer: `MonthlySummaryRepo.get`).

## `save` (upsert)

```python
def save(
    self,
    asin: str,
    year: int,
    month: int,
    total_units: int,
    total_profit: float,
    days_with_data: int,
) -> None:
    """Insert or overwrite the summary row for (asin, year, month).

    Idempotent — safe to call repeatedly for the same month (e.g. manual
    re-run of the monthly job); the existing row is replaced, not duplicated.
    """
```

```sql
INSERT INTO book_monthly_summary
    (asin, year, month, total_units, total_profit, days_with_data, computed_at)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (asin, year, month) DO UPDATE SET
    total_units = excluded.total_units,
    total_profit = excluded.total_profit,
    days_with_data = excluded.days_with_data,
    computed_at = excluded.computed_at
```

`computed_at` = `datetime.now(timezone.utc).isoformat()`, matching the
`added_at` convention already used in `BookRepo.register_book`.

## `get` (single month)

```python
def get(self, asin: str, year: int, month: int) -> MonthlySummary | None:
    """Return the precomputed summary for one (asin, year, month), or None
    if it hasn't been computed yet."""
```

```sql
SELECT asin, year, month, total_units, total_profit, days_with_data
FROM   book_monthly_summary
WHERE  asin = ? AND year = ? AND month = ?
```

## `get_many` (batch, for `Helper_Pdf_Metrics`)

`Helper_Pdf_Metrics.compute()` needs one lookup per distinct `(year,
month)` bucket found in a book's snapshot history (see
[06](./06-metrics-integration.md)) — expose a batch method so it isn't
N+1 querying per PDF page when a book has many months of history:

```python
def get_many(self, asin: str) -> dict[tuple[int, int], MonthlySummary]:
    """Return every precomputed summary row for *asin*, keyed by (year, month)."""
```

```sql
SELECT asin, year, month, total_units, total_profit, days_with_data
FROM   book_monthly_summary
WHERE  asin = ?
```

## Test coverage

New `tests/test_monthly_summary_repo.py`, mirroring
`tests/test_snapshot_repo.py`'s `tmp_db` fixture pattern:

- `save` then `get` round-trips the exact values written.
- `save` called twice for the same `(asin, year, month)` with different
  numbers updates the row in place — `get` returns the *second* call's
  values, and a raw `SELECT COUNT(*)` confirms only one row exists (proves
  upsert, not insert-duplicate).
- `get` returns `None` for a month never saved.
- `get_many` returns all months for one ASIN keyed correctly, and does not
  return rows belonging to a different ASIN seeded in the same test.
