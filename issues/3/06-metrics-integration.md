# 6. `Helper_Pdf_Metrics` — read precomputed rows, fall back to live calc

## Where

`reports/Helper_Pdf_Metrics.py::Helper_Pdf_Metrics.compute()`, the monthly
bucketing loop currently at lines 91-123.

## Current behavior (for reference)

```python
monthly: defaultdict[tuple[int, int], dict[str, int | float]] = defaultdict(_empty_bucket)
for i, d in enumerate(dates):
    ym = (d.year, d.month)
    if ym == current_ym:
        continue
    bucket = monthly[ym]
    bucket["total_units"] += units_per_day[i]
    bucket["total_profit"] += profit_per_day[i]
    bucket["days_with_data"] += 1

monthly_rows: list[MonthlyRow] = []
for ym in sorted(monthly):
    bucket = monthly[ym]
    ...  # format into MonthlyRow
```

This always recomputes every past month from `dates`/`units_per_day`/
`profit_per_day`, which are themselves derived from the (now full-history,
per Issue 3's predecessor fix) `snapshot_rows`.

## New behavior

1. `Helper_Pdf_Metrics.__init__` takes an optional injected
   `MonthlySummaryRepo`, following the same constructor-injection pattern
   `Helper_Pdf_Loader(repo: BookRepo)` already uses:

   ```python
   def __init__(self, monthly_repo: MonthlySummaryRepo | None = None) -> None:
       self._monthly_repo = monthly_repo or MonthlySummaryRepo()
   ```

   `Service_Pdf_GenFromAsin.run()` (`reports/Service_pdf_genFromAsin.py:82`)
   changes from `Helper_Pdf_Metrics().compute(raw)` to constructing one
   `MonthlySummaryRepo()` and passing it in — cheap either way since SQLite
   connections are opened per-call, but keeps the DI path consistent with
   `Helper_Pdf_Loader(repo)` right above it in the same loop.

2. Before recomputing a month's bucket, check
   `self._monthly_repo.get_many(data["asin"])` (call once per `compute()`
   invocation, not once per month, to avoid N queries) for a precomputed
   `MonthlySummary` at that `(year, month)` key:

   ```python
   precomputed = self._monthly_repo.get_many(data["asin"])
   ...
   for ym in sorted({(d.year, d.month) for d in dates if (d.year, d.month) != current_ym}):
       stored = precomputed.get(ym)
       if stored is not None:
           total_units = stored["total_units"]
           total_profit = stored["total_profit"]
           days_with_data = stored["days_with_data"]
       else:
           # existing live-aggregation fallback, scoped to this month's dates
           total_units, total_profit, days_with_data = aggregate_month(
               [row for row, d in zip(rows, dates) if (d.year, d.month) == ym],
               profit_pct,
           )
       ...  # format into MonthlyRow same as today
   ```

   Uses the `aggregate_month()` helper extracted in
   [04](./04-monthly-job.md) for the fallback path, so the formula is
   defined exactly once for both the cron job and this fallback.

3. `MonthlyRow` (the `TypedDict`/`NamedTuple` shape returned to
   `Helper_Pdf_Renderer`) is unchanged — this is purely a data-*source*
   change, not a shape change, so `reports/Helper_Pdf_Renderer.py`'s
   monthly-table rendering needs no edits.

## Test coverage

Extend `tests/test_pdf_metrics.py`:

- A month with a `MonthlySummaryRepo.get_many` hit uses the stored numbers
  verbatim, even if they'd differ from what live aggregation of the passed
  `snapshot_rows` would produce (proves it's actually reading the stored
  value, not silently still recomputing) — mock `MonthlySummaryRepo` to
  return a deliberately "wrong" number and assert it appears in the output
  `MonthlyRow`.
- A month with no stored row falls back to live aggregation and produces
  the same numbers as today's pre-change behavior (regression check —
  reuse/adapt whatever fixture the existing monthly-table tests already
  use).
- Current month is still always excluded regardless of what
  `MonthlySummaryRepo` returns for it (the job never computes/stores the
  current month per `main.md`'s scope decision, but guard the read path
  too — don't display a current-month row even if one somehow exists in
  the table, e.g. from a clock/timezone edge case).
