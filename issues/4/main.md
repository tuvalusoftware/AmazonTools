# Plan: Persist cron run history (queryable by time, ASIN, and cron type)

> GitHub issue: TBD (no remote configured yet).

## Context

Three cron jobs are registered in `main.py` via APScheduler:

- `scrape_bsr` (`jobs/scrape_bsr.py`) — daily, loops over
  `BookRepo().load_active_books()`, one BSR/price fetch per ASIN. Since
  [issue 3](../3/07-backfill-missed-months.md), it also calls
  `sync_missing_months(asin)` (from `jobs/monthly_summary.py`) inline for
  each ASIN right after a successful snapshot save.
- `monthly_summary` (`jobs/monthly_summary.py`) — monthly, loops over
  `SnapshotRepo().list_asins_that_have_data()` (active or not), calling the
  same `sync_missing_months(asin)` for each.
- `email_digest` (`jobs/email_digest.py`) — weekly, not per-ASIN: groups
  active books by author email and sends one digest per author.

The only record of what happened on any run today is free-text log lines
via `utils/logger.py` — stdout plus a `TimedRotatingFileHandler` file
(`LOG_DIR/scraper.log`, rotated daily, 14-day retention). There is no
structured record of *which cron ran, for which ASIN, when, and with what
result* that can be queried or filtered — only grepping log text, which
disappears after 14 days.

**Decisions**:

1. **One SQLite table**, following the exact pattern of `book_monthly_summary`
   ([issue 3, step 1](../3/01-schema.md)): plain columns, no JSON blob for
   the filterable dimensions (`cron_type`, `asin`, `started_at`) so they can
   be indexed and queried with normal `WHERE`/`ORDER BY` — a free-text
   `detail` column carries the non-filterable extra info (counts, error
   message).
2. **Granularity**: one row per unit of work, not one row per whole job
   invocation — this is what makes "which ASIN" queryable:
   - `scrape_bsr` → one row per ASIN per scrape attempt.
   - `monthly_summary` → one row per ASIN per `sync_missing_months` call
     (both from the monthly cron and from the daily `scrape_bsr` trigger —
     distinguished via the `trigger` column, see
     [02](./02-cron-run-repo.md)).
   - `email_digest` → one row per whole run, `asin` left `NULL` (the job
     isn't per-ASIN — it's grouped by author email).
3. **Storage lives in the same SQLite DB** (`settings.DB_PATH`) as every
   other table, written through a new `CronRunLogRepo`, called directly on
   an instance from each job — same convention as `BookRepo`,
   `SnapshotRepo`, `MonthlySummaryRepo` (per `CLAUDE.md`: no module-level
   helper functions wrapping repo methods).
4. **No new web/API endpoint or UI** in this issue — querying/filtering is
   exposed as `CronRunLogRepo` methods only (callable from a Python shell,
   a future script, or a future web route). Keeps this issue scoped to
   storage + write-through instrumentation.

## Technical checklist

- [x] [1. New `cron_run_log` table](./01-schema.md)
- [x] [2. `CronRunLogRepo` — write + filterable query methods](./02-cron-run-repo.md)
- [x] [3. Wire logging into the three jobs](./03-job-integration.md)

## Out of scope

- Web UI or API route to browse run history — `CronRunLogRepo` methods are
  enough for now; a route can be added later on top of the same repo
  without schema changes.
- Retention/pruning policy for old rows (the log file already rotates out
  after 14 days; this table will grow unbounded until a follow-up decides
  a policy — flagged here, not solved here).
- Alerting on repeated failures — out of scope, this issue only persists
  the data needed to build that later.
- Changing what `sync_missing_months` or `_scrape_bsr` actually compute —
  this issue only wraps their existing call sites with logging.

## Manual test

- [ ] Run `make run` (`jobs.scrape_bsr.run()`) for at least one active ASIN
      → one `cron_run_log` row appears with `cron_type='scrape_bsr'`, that
      `asin`, and `status='success'`.
- [ ] Run the monthly job manually
      (`python -c "from jobs.monthly_summary import run; run()"`) for an
      ASIN with a backfill gap → one `cron_run_log` row per ASIN with
      `cron_type='monthly_summary'`, `trigger='cron'`.
- [ ] Trigger a scrape for an ASIN with a missing summary month → confirm a
      second `cron_run_log` row appears with `cron_type='monthly_summary'`,
      `trigger='scrape_bsr'`, same `asin`, in addition to the
      `cron_type='scrape_bsr'` row for that scrape.
- [ ] Force a failure (e.g. temporarily break DB path or raise inside
      `_scrape_bsr`) → row is written with `status='failure'` and a non-empty
      `detail` (error message), not silently dropped.
- [ ] Run the digest job → one row with `cron_type='email_digest'`,
      `asin IS NULL`.
- [ ] Query `CronRunLogRepo().query(cron_type="scrape_bsr", asin="B0XXXXXXX")`
      and `CronRunLogRepo().query(start_time=..., end_time=...)` from a shell
      → results are filtered as expected.

## Verification

```
make test    # must stay green (unit + no-integration)
```
