# Plan: Precompute monthly profit summary per ASIN

> GitHub issue: TBD (no remote configured yet).

## Context

`Helper_Pdf_Metrics.compute()` recomputes the "Monthly Profit" table from
scratch on every PDF generation, scanning **all** historical snapshot rows
(`Service_Pdf_GenFromAsin.DAYS` is now `0`, full history). Cost grows
unboundedly, even though past months are immutable once elapsed.

## Decisions

- **Trigger**: new monthly cron job (start of each calendar month) computes
  the just-completed month for every ASIN and upserts into a new table.
- **Scope**: all ASINs with any `bsr_snapshots` row, active or not.
- **Backfill**: in scope, self-healing — each run walks every completed
  month between an ASIN's earliest snapshot and last month (not just "last
  month"), skipping months that already have a stored row. This recovers
  automatically from a missed cron run (app down/crashed/redeployed over a
  month boundary) without a separate manual backfill step. See
  [7](./07-backfill-missed-months.md). Months still missing a row (e.g.
  before this job's first-ever successful run) keep falling back to live
  aggregation from `bsr_snapshots`, per [6](./06-metrics-integration.md).
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
- [ ] [7. Self-healing backfill for missed monthly runs](./07-backfill-missed-months.md)

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

## Verification

```
make test    # must stay green (unit + no-integration)
```
