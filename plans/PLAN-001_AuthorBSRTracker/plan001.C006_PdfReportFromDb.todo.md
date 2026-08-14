# PLAN-001 — C006: PDF Performance Report from Live DB Data

← [plan001.main.md](plan001.main.md)

Replaces the fully-mocked `reports/mock_charts.py` with a real pipeline that
reads `bsr_snapshots` and `tracked_books` from SQLite, computes derived metrics
(estimated units sold, daily profit, cumulative series), and writes a multi-page
PDF identical in layout to the mock — one page per book, five pages per book.

**Depends on:** [plan001.C002_BsrJobExtension.todo.md](plan001.C002_BsrJobExtension.todo.md), [plan001.C004A_PriceScraping.todo.md](plan001.C004A_PriceScraping.todo.md), [plan001.C006A_PdfTypes.todo.md](plan001.C006A_PdfTypes.todo.md)

> **Future note:** An `income_summary` table will be added to the DB to persist the
> aggregated monthly income per book (one row per asin + month). When that table exists,
> the monthly table page should read from `income_summary` directly instead of
> re-computing from `bsr_snapshots`. The computation logic in `_compute_metrics` is the
> interim source until `income_summary` is available.

---

## File structure — `reports/` sub-package

> **Architecture note:** `Service_pdf_genFromAsin.py` is the sole public entry point.
> It exposes one class (`Service_Pdf_GenFromAsin`) with one public method (`run`).
> All helpers are grouped into focused sub-classes living in separate files within `reports/`.

> **C006A applied:** types live in their producer modules — no `_types.py` central file.
> `DailySnapshotRow` → `utils/Repo_Snapshot.py`
> `BookRawData`      → `reports/Helper_Pdf_Loader.py`
> `MonthlyRow`, `BookMetricsData` → `reports/Helper_Pdf_Metrics.py`

```
reports/
├── __init__.py                         ← created (empty)
├── Service_pdf_genFromAsin.py          ← entry point; class Service_Pdf_GenFromAsin
├── Helper_Pdf_Loader.py                ← class Helper_Pdf_Loader   (data-loading layer) + BookRawData
├── Helper_Pdf_Metrics.py               ← class Helper_Pdf_Metrics  (metric computation) + MonthlyRow, BookMetricsData
└── Helper_Pdf_Renderer.py              ← class Helper_Pdf_Renderer (rendering helpers + page builder)
```

---

## `reports/Service_pdf_genFromAsin.py` — entry-point class

- [x] Create `reports/Service_pdf_genFromAsin.py`
- [x] Top-of-file constants (no config dependency — all tunable here):
  ```python
  DAYS = 30           # rolling window queried from bsr_snapshots
  OUTPUT_PATH = Path(__file__).parent / "book_performance_report.pdf"
  ```
  Note: `MONTHLY_MONTHS` is **removed** — the monthly table shows all complete months
  present in `bsr_snapshots` for that ASIN, however many there are.
- [x] Define class `Service_Pdf_GenFromAsin`:
  - Constructor: `__init__(self, asin_filter=None, output_path=None)`
    - `asin_filter`: optional single ASIN string; `None` means all active books
    - `output_path`: optional `Path`; falls back to `OUTPUT_PATH` constant
  - Single public method: `run(self) -> Path`
    - Instantiates `BookRepo()` once — DB path always comes from `settings.DB_PATH`
    - Collects active ASINs: if `asin_filter` is set use `[asin_filter]`, else query `load_active_books()` and extract `asin` values
    - For each ASIN:
      1. `Helper_Pdf_Loader(repo).load(asin, DAYS)` → `BookRawData | None`
      2. Skip with `logging.warning(...)` if `None`
      3. `Helper_Pdf_Metrics().compute(data)` → `BookMetricsData`
      4. `Helper_Pdf_Renderer(pdf).render_book(data)` inside the open `PdfPages` context
    - Logs path after writing; returns the resolved `output_path`
- [x] Accept an optional `--output` CLI flag via `argparse` to override `OUTPUT_PATH`
- [x] Accept an optional `--asin` CLI flag to restrict the report to a single ASIN
  - Default: report covers all active books in `tracked_books`
- [x] Guard `if __name__ == "__main__":` instantiates `Service_Pdf_GenFromAsin(...)` and calls `.run()`

---

## `reports/Helper_Pdf_Loader.py` — data-loading sub-class

> **C006A applied:** `BookRawData` TypedDict is already defined in this file.
> `Helper_Pdf_Loader` class stub is already created with the correct signature.

- [x] Create `reports/Helper_Pdf_Loader.py` — done by C006A
- [x] Implement class `Helper_Pdf_Loader`:
  - Constructor: `__init__(self, repo: BookRepo)`
  - Method `load(self, asin: str, days: int) -> BookRawData | None`:
    - Query `tracked_books` via `repo.load_active_books()` to get `title`, `profit_pct`
    - Fall back to `profit_pct = 0.70` if the book row is missing or `profit_pct` is 0
    - Delegate snapshot query to `SnapshotRepo().load_daily_snapshots(asin)` (all rows, oldest-first)
    - Return `None` if fewer than 2 rows exist (caller logs WARNING)
    - Return `BookRawData`:
      ```python
      {
        "asin": str,
        "title": str,
        "profit_pct": float,
        "snapshot_rows": [DailySnapshotRow, ...]   # oldest-first; key is snapshot_rows not rows
      }
      ```

---

## `reports/Helper_Pdf_Metrics.py` — metric computation sub-class

> **C006A applied:** `MonthlyRow` (NamedTuple) and `BookMetricsData` (TypedDict) are already
> defined in this file.  `Helper_Pdf_Metrics` class stub is already created.

- [x] Create `reports/Helper_Pdf_Metrics.py` — done by C006A
- [x] Implement class `Helper_Pdf_Metrics`:
  - Single method `compute(self, data: BookRawData) -> BookMetricsData`:
    - Iterate over `data["snapshot_rows"]` (not `data["rows"]`)
    - For each daily row compute:
      - `estimated_units = max(1, round(10_000 / rank ** 0.70))` — same power-law as mock
      - `daily_profit = estimated_units * price * profit_pct`
        - Use `price` from the snapshot row; fall back to `0.0` when `price == 0`
    - Derive cumulative series with `itertools.accumulate`
    - Build monthly buckets (`(year, month)` keys) from **all rows** in `data["snapshot_rows"]`:
      - **Only include complete calendar months** — exclude the current (partial) month
      - Show **all complete months** present in the data — no fixed cap
      - Aggregate `total_units`, `total_profit`, `days_with_data` per month
      - `avg_daily_profit = total_profit / days_with_data`
    - Return `BookMetricsData` (all fields from *data* plus):
      ```python
      {
        "dates": [date, ...],           # datetime.date objects
        "date_labels": [str, ...],      # "Aug 01" formatted
        "units_per_day": [int, ...],
        "profit_per_day": [float, ...],
        "cumulative_units": [int, ...],
        "cumulative_profit": [float, ...],
        "monthly_rows": [MonthlyRow(...), ...]   # MonthlyRow NamedTuple, not bare tuple
      }
      ```

---

## `reports/Helper_Pdf_Renderer.py` — rendering sub-class

> **C006A applied:** `Helper_Pdf_Renderer` stub is already created, importing
> `BookMetricsData` and `MonthlyRow` from their owning modules.

- [x] Create `reports/Helper_Pdf_Renderer.py` — done by C006A (stub with correct imports)
- [x] Port layout helpers from `mock_charts.py` as **private static methods** of `Helper_Pdf_Renderer`:
  - `_style_ax`, `_new_page`, `_save_page`, `_sparse_labels`
  - `_add_description(ax_desc, key, price, profit_pct)` — `price` and `profit_pct` parameters so formula strings show real values per book
  - `DESCRIPTIONS` dict — profit-formula strings reference the passed-in `price` (live value) instead of a module-level constant
  - `DESCRIPTIONS["monthly_table"]` body: `"All complete calendar months with data (first-to-first).\nThe current partial month is excluded — each row spans exactly one full month."`
- [x] Implement `render_book(self, data: BookMetricsData) -> None`:
  - Page header prefix: `"[{title}] — "` prepended to each chart title
  - **Page 1** — Estimated Books Sold per Day (bar chart, `#4a90d9`)
  - **Page 2** — Estimated Daily Profit (bar chart, `#e07b39`)
  - **Page 3** — Cumulative Estimated Profit (line + fill, `green`)
  - **Page 4** — Cumulative Estimated Books Sold (line + fill, `#4a90d9`)
  - **Page 5** — Monthly Profit Summary (table, same column headers and alternating-row styling as mock)
  - Sparse X-axis tick every 2nd date (`step=2`) to avoid label crowding
  - If `monthly_rows` is empty, render a single "No monthly data yet" row in the table
  - Access `data["snapshot_rows"]` for raw rows; `data["monthly_rows"]` contains `MonthlyRow` NamedTuples

---

## `utils/registry.py` — query helper for date-grouped BSR

> **C006A applied:** `load_daily_snapshots` lives in `SnapshotRepo` (`utils/Repo_Snapshot.py`),
> not in `BookRepo`.  `Helper_Pdf_Loader` must import and instantiate `SnapshotRepo` directly.

- [x] `load_daily_snapshots` is implemented in `SnapshotRepo.load_daily_snapshots()` — do **not** add it to `BookRepo`
- [ ] In `Helper_Pdf_Loader.load()`, instantiate `SnapshotRepo()` and call `.load_daily_snapshots(asin)` instead of `repo.load_daily_snapshots(asin)`
- [ ] The rolling-window `DAYS = 30` constant is used **only** for the daily bar/line charts (pages 1–4); the monthly table uses the full history returned by `SnapshotRepo().load_daily_snapshots(asin, days=0)`

---

## `reports/__init__.py`

- [x] Create empty `reports/__init__.py` — done by C006A

---

## PDF delivery — daily email attachment (via C003)

> The PDF is **not** scheduled separately. `jobs/email_digest.py` generates the PDF as part of
> its daily run and attaches it to each author's digest email. No new cron job or env var is needed.

- [x] In `jobs/email_digest.py`, call `Service_Pdf_GenFromAsin(asin_filter=None, output_path=tmp_path).run()` once per email batch
  - Generate the PDF into a `tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)` path
  - Pass the resulting `Path` to `send_email(...)` as an `attachment` parameter
  - Delete the temp file after all emails for that run have been sent
- [x] Update `send_email(to, subject, html_body, attachment: Path | None = None)` in `jobs/email_digest.py`:
  - When `attachment` is not `None`, wrap the message in `MIMEMultipart("mixed")` instead of `"alternative"`
  - Attach the HTML part as a `MIMEMultipart("alternative")` sub-part
  - Read the PDF bytes and attach as `MIMEApplication(pdf_bytes, Name=attachment.name)` with
    `Content-Disposition: attachment; filename="<attachment.name>"`
  - When `attachment` is `None`, behaviour is unchanged (send HTML-only email)
- [x] PDF filename convention: `bsr_report_YYYY-MM-DD.pdf` (today's UTC date)
  — set this as the `output_path` when calling `Service_Pdf_GenFromAsin`

---

## Verification

- [ ] `python reports/Service_pdf_genFromAsin.py` with at least one active ASIN and ≥ 2 days of `bsr_snapshots` rows — confirm PDF is written to `reports/book_performance_report.pdf`
- [ ] Open the PDF — confirm 5 pages per tracked book; title prefix `[Book Title] —` visible on each page
- [ ] Confirm `price` shown in description panels matches the latest scraped price from `bsr_snapshots`, not the seed `0.0` from `tracked_books`
- [ ] `python reports/Service_pdf_genFromAsin.py --asin B0XXXXXXXX` — confirm only that book's pages appear in the PDF
- [ ] `python reports/Service_pdf_genFromAsin.py --output /tmp/test.pdf` — confirm PDF written to the custom path
- [ ] Run with an ASIN that has 0 or 1 snapshot rows — confirm it is skipped with a WARNING log, no crash
- [ ] Run with no active books in DB — confirm empty PDF is still created without error
- [ ] Trigger `jobs/email_digest.run()` manually — confirm the received email contains the PDF as an attachment named `bsr_report_<today>.pdf`
- [ ] Confirm the temp PDF file is deleted after the digest run completes
