# 1. New `cron_run_log` table

## Where

`utils/registry.py` — follow the existing pattern used for `_CREATE_TABLE`
/ `_CREATE_BSR_SNAPSHOTS_TABLE` / `_CREATE_MONTHLY_SUMMARY_TABLE` (module-level
SQL constants, executed from `BookRepo.init_db()`).

## Schema

```sql
CREATE TABLE IF NOT EXISTS cron_run_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    cron_type    TEXT    NOT NULL,   -- 'scrape_bsr' | 'monthly_summary' | 'email_digest'
    asin         TEXT,               -- NULL for non-per-ASIN runs (email_digest)
    trigger      TEXT    NOT NULL,   -- 'cron' | 'scrape_bsr' | 'manual' — what caused this row
    started_at   TEXT    NOT NULL,   -- ISO-8601 UTC
    finished_at  TEXT    NOT NULL,   -- ISO-8601 UTC
    status       TEXT    NOT NULL,   -- 'success' | 'failure'
    detail       TEXT                -- free-form: counts, error message; NULL when nothing to add
);

CREATE INDEX IF NOT EXISTS idx_cron_run_log_cron_type_started_at
    ON cron_run_log (cron_type, started_at);

CREATE INDEX IF NOT EXISTS idx_cron_run_log_asin
    ON cron_run_log (asin);

CREATE INDEX IF NOT EXISTS idx_cron_run_log_started_at
    ON cron_run_log (started_at);
```

- `id` is a plain surrogate key — unlike `book_monthly_summary`, there is no
  natural unique key to upsert on: every run is a new row, never overwritten
  (this is a log, not a cache).
- `trigger` disambiguates the two paths that both write
  `cron_type='monthly_summary'` rows for the same ASIN: the monthly cron
  itself (`'cron'`) vs. the inline call from `scrape_bsr`'s daily loop
  (`'scrape_bsr'`), per [issue 3, step 7](../3/07-backfill-missed-months.md).
  `scrape_bsr` and `email_digest` rows always use `trigger='cron'` when run
  from the scheduler; a manual invocation (`make run`, a shell one-liner)
  should pass `trigger='manual'` — see [02](./02-cron-run-repo.md) for how
  callers set this.
- Three separate single-column/composite indexes (not one wide composite)
  because the three filter dimensions in the requirement — time range,
  ASIN, cron type — are each used independently, not always all three
  together; `(cron_type, started_at)` covers the common "history for this
  job type, most recent first" query, and the other two support filtering
  by ASIN or by time range alone.
- `status`/`detail` are intentionally unconstrained TEXT (no CHECK
  constraint) — same minimal-schema style as the rest of this codebase
  (`book_monthly_summary` has no CHECK constraints either).

## `BookRepo.init_db()` changes

Add the new table + indexes to the `with conn:` block alongside the
existing three:

```python
with conn:
    conn.execute(_CREATE_TABLE)
    conn.executescript(_CREATE_BSR_SNAPSHOTS_TABLE)
    conn.executescript(_CREATE_MONTHLY_SUMMARY_TABLE)
    conn.executescript(_CREATE_CRON_RUN_LOG_TABLE)
```

No migration step needed (fresh `CREATE TABLE IF NOT EXISTS`, no existing
data to migrate).

## Test coverage

Extend `tests/test_registry.py` with one assertion that `cron_run_log`
exists after `init_db()`, e.g. via `PRAGMA table_info('cron_run_log')`
returning non-empty — same style as the existing
`book_monthly_summary` assertion.
