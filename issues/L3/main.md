# Plan: Precompute monthly profit summary per ASIN

> GitHub issue: TBD (no remote configured yet).

## Context

`Helper_Pdf_Metrics.compute()` recomputes the "Monthly Profit" table from
scratch on every PDF generation, scanning **all** historical snapshot rows
(`Service_Pdf_GenFromAsin.DAYS` is now `0`, full history). Cost grows
unboundedly, even though past months are immutable once elapsed.

## Decisions

- **Trigger**: two triggers share one self-healing function
  (`sync_missing_months(asin)`, see [7](./07-backfill-missed-months.md)):
  - the monthly cron job (start of each calendar month), which sweeps
    every ASIN with any snapshot history, active or not;
  - the daily `scrape_bsr` job, which calls it for a single ASIN right
    after successfully saving that ASIN's snapshot for the day — so a
    missed cron run doesn't need to wait up to a month to self-heal for
    any ASIN still being actively scraped.
- **Scope**: all ASINs with any `bsr_snapshots` row, active or not, are
  covered by the monthly cron; the daily trigger only covers active ASINs
  (`scrape_bsr` only iterates `load_active_books()`), so unsubscribed
  ASINs rely on the monthly cron alone.
- **Backfill**: in scope, self-healing — each call walks every completed
  month between an ASIN's earliest snapshot and last month (not just "last
  month"), skipping months that already have a stored row. This recovers
  automatically from a missed cron run (app down/crashed/redeployed over a
  month boundary) without a separate manual backfill step, and for active
  ASINs recovers on the very next successful daily scrape rather than
  waiting for the next monthly cron. See [7](./07-backfill-missed-months.md).
  Months still missing a row (e.g. before this job's first-ever successful
  run) keep falling back to live aggregation from `bsr_snapshots`, per
  [6](./06-metrics-integration.md).
- Daily/cumulative chart data is untouched — still computed live.
- `Helper_Pdf_Metrics.compute()` reads the precomputed row first, falls back
  to live calc when missing.
- Table is a write-once cache per `(asin, year, month)`; upsert-safe, no
  staleness/versioning logic.
- Current (in-progress) month stays excluded from `monthly_rows`, unchanged.

## Technical checklist

- [x] [1. New `book_monthly_summary` table](./01-schema.md)
- [x] [2. `SnapshotRepo` — month-scoped query + distinct-ASIN listing](./02-snapshot-repo.md)
- [x] [3. `MonthlySummaryRepo` — read/write access to the new table](./03-monthly-summary-repo.md)
- [x] [4. `jobs/monthly_summary.py` — the new monthly cron job](./04-monthly-job.md)
- [x] [5. Wire the job into the scheduler, config, and manual runner](./05-scheduling.md)
- [x] [6. `Helper_Pdf_Metrics` — read precomputed rows, fall back to live calc](./06-metrics-integration.md)
- [x] [7. Self-healing backfill for missed monthly runs](./07-backfill-missed-months.md)

## Out of scope

- One-off manual backfill tooling (a script/CLI to force-recompute an
  arbitrary historical range) — the self-healing walk in
  [7](./07-backfill-missed-months.md) covers the "app was down" case
  without needing a separate tool.
- Pruning/archiving raw `bsr_snapshots` (pre-existing, separate concern).
- Staleness detection/versioning for stored rows.
- Exposing monthly summary via web UI.

## Manual test

- [ ] Seed two months of snapshots for one ASIN, run `make run-job` →
      confirm one row per completed month with correct
      `total_units`/`total_profit`/`days_with_data`.
- [ ] Re-run the job → row is upserted, not duplicated.
- [ ] Generate a PDF for an ASIN with one precomputed month + one older
      month (no row) → both show correct numbers (one read, one live).
- [ ] Unsubscribed-mid-month ASIN still gets a row for its data month.
- [ ] Seed 3 months of snapshots for an ASIN, run the job once (only the
      most recent completed month should be missing a row — simulating a
      normal single run) → confirm all missing completed months get a row
      in one run, not just the latest.
- [ ] Seed an active ASIN with a gap month (missing summary row) and run
      `scrape_bsr`'s job for it → after that scrape, the gap month has a
      row without waiting for the monthly cron.

## Verification

```
make test    # must stay green (unit + no-integration)
```
