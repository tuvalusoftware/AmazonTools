# 1. New `book_monthly_summary` table

## Where

`utils/registry.py` — follow the existing pattern used for
`_CREATE_TABLE` / `_CREATE_BSR_SNAPSHOTS_TABLE` (module-level SQL
constants, executed from `BookRepo.init_db()`).

## Schema

```sql
CREATE TABLE IF NOT EXISTS book_monthly_summary (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    asin          TEXT    NOT NULL,
    year          INTEGER NOT NULL,
    month         INTEGER NOT NULL,   -- 1-12
    total_units   INTEGER NOT NULL,
    total_profit  REAL    NOT NULL,
    days_with_data INTEGER NOT NULL,
    computed_at   TEXT    NOT NULL,   -- ISO-8601 UTC, when this row was (re)computed
    UNIQUE (asin, year, month)
);
```

- `UNIQUE (asin, year, month)` is what makes the upsert in
  `MonthlySummaryRepo.save()` (see [03](./03-monthly-summary-repo.md)) safe
  to re-run — `INSERT ... ON CONFLICT (asin, year, month) DO UPDATE SET ...`.
- No `avg_str`/`profit_str`/formatted fields — those are presentation-layer
  string formatting done in `Helper_Pdf_Metrics.compute()` today
  (`f"${total_profit:,.2f}"` etc.) and should stay there; the table stores
  raw numbers only, same separation `bsr_snapshots` already has (raw
  `rank`/`price`, formatting happens downstream).

## `BookRepo.init_db()` changes

Add the new `CREATE TABLE` constant to the `with conn:` block alongside the
existing two:

```python
with conn:
    conn.execute(_CREATE_TABLE)
    conn.executescript(_CREATE_BSR_SNAPSHOTS_TABLE)
    conn.executescript(_CREATE_MONTHLY_SUMMARY_TABLE)
```

No migration step needed (fresh `CREATE TABLE IF NOT EXISTS`, no existing
data to migrate — this table doesn't exist yet anywhere).

## Test coverage

Extend `tests/test_registry.py` (or wherever `BookRepo.init_db()` is
currently tested) with one assertion that `book_monthly_summary` exists
after `init_db()`, e.g. via
`PRAGMA table_info('book_monthly_summary')` returning non-empty.
