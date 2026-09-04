# 6. Storage & code layout

> Per **D1 DECIDED (standalone dataset)** in `01-purpose-and-scope.md`: the
> store must be self-contained — no foreign keys into `tracked_books` /
> `bsr_snapshots` and no shared IDs. Open sub-decision: keep it as a new
> table inside the existing `DB_PATH` SQLite file (simplest, still logically
> separate) vs. a dedicated `PUBLISHER_DB_PATH` file (cleaner isolation,
> trivially portable as a hand-off artifact). Leaning toward a **dedicated
> file** since the dataset is meant to be exported/handed over, not queried
> alongside tracker data.

## Table design

| Option | Notes |
|---|---|
| A. One `publisher_books` table with a `publisher` column | one schema, one repo, easy cross-publisher export; matches the flat-column style of `book_monthly_summary` / `cron_run_log` |
| B. One table per publisher (`manning_books`, `oreilly_books`) | isolates site-specific quirks; more code, awkward to query together |

**Recommendation: A.** Columns per `02-fields-and-schema.md`
recommendation: `id, publisher, title, author, category, product_url
(unique), isbn13 (unique, nullable), format, publication_date, scraped_at`.

## Repo class
- New `PublisherCatalogRepo` in `utils/` following the existing convention:
  called directly on an instance (`PublisherCatalogRepo().upsert_book(...)`),
  **no** module-level wrapper functions, **no** module-level singleton
  (per `CLAUDE.md`).
- Methods (names to finalize in the implementation issue):
  - `upsert_book(record)` — insert or update on `product_url`
  - `list_books(publisher=None, category=None)` — for export / UI
  - `count(publisher=None)`

## Job vs script

| Option | Notes |
|---|---|
| `scripts/` one-off (like `Helper_Lookup_Asin.py`) | fits "one-off export" outcome; run by hand via `run_job.py` |
| `jobs/` module + APScheduler entry (like `scrape_bsr`) | fits "ongoing refresh" outcome; needs a `*_CRON` setting |

**Recommendation:** start as a `scripts/` one-off; promote to `jobs/` only
if the manager wants a scheduled refresh (open question 5). Either way the
crawl logic should live in a plain module both can call.

## Config additions (if implemented)
- `MANNING_CATALOG_URL`, `OREILLY_CATALOG_URL`
- `PUBLISHER_SCRAPE_DELAY` (politeness gap)
- `MANNING_AFFILIATE_PARAMS` (export-time, optional)
- O'Reilly creds only if D5 authorizes an account
