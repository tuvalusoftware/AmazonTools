# 7–8. Delivery format & scheduling

## D7 — Delivery / output format

**The request does not say what the manager wants to do with the data.**
This must be asked (open question 1). Options:

| Option | Fit | Effort |
|---|---|---|
| CSV / Excel export | hand-off, offline analysis, sharing | low — one exporter over `PublisherCatalogRepo.list_books()`; `utils/storage.py` already writes JSON/CSV |
| JSON dump | feeding another tool | low |
| Web UI page | browse/filter inside the existing FastAPI app (`web/app.py`) | medium — new route + template |
| Emailed report | recurring digest, like `email_digest.py` | medium — template + schedule |
| Queryable DB only | other code consumes it | none beyond the table |

**Recommendation:** CSV export for v1 (most likely what "give me the list"
means), with the SQLite table as the source of truth so other formats can be
added later. Confirm before building.

## D8 — Scheduling

| Option | Notes |
|---|---|
| One-off manual run | matches a one-time data request; no cron |
| Recurring cron | keeps the dataset fresh; needs frequency + full-vs-incremental decision |

If recurring:
- Frequency — weekly or monthly is plenty for a publisher catalog (new
  titles appear slowly). Reuse the `*_CRON` + `TIMEZONE` pattern from
  `config.py`.
- Full re-scrape vs incremental — full is simplest and fine at this
  cadence/size; `scraped_at` + upsert on `product_url` already gives
  "new/changed" detection for free. Detecting **removed** titles needs a
  per-run sweep flag — defer unless asked.

**Recommendation:** one-off for v1; revisit scheduling after the first run
shows the manager what the data looks like.
