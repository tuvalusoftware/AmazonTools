# 1–2. Purpose & catalog scope

## D1 — What is this dataset for?

| Option | Meaning | Implication |
|---|---|---|
| A. Standalone catalog | Just produce a list of Manning/O'Reilly books with title/author/category. Nothing connects to the Amazon tracker. | Smallest scope. New table + exporter only. |
| B. Discovery feed for the tracker | Use scraped titles to look up ASINs (`scripts/Helper_Lookup_Asin.py`) and enrol them into `tracked_books` for BSR tracking. | Much larger; depends on ASIN match quality; needs manager approval on auto-enrolment. |
| C. Reference data alongside tracker | Store the catalog, surface it in the web UI / reports for context, no automatic tracking. | Medium. |

**Recommendation: A** for this issue. B/C can be a follow-up once the raw
dataset exists. Confirm with manager (open question 1).

> **DECIDED (2026-09-04): Option A — standalone dataset.**
> The publisher catalog is kept as its own separate dataset, physically and
> logically distinct from the Amazon BSR tracker's data. It does **not** feed
> `tracked_books`, is not joined to `bsr_snapshots`, and is not surfaced
> through the existing tracker UI/reports. Any later integration (ASIN
> lookup, cross-referencing) is a separate future issue, not assumed here.
> Practical consequence: see `05-storage-and-layout.md` — favour a
> self-contained store (own table, arguably its own SQLite file) and its own
> exporter, with no foreign keys into existing tables.

## D1b — One-off vs ongoing

| Option | Notes |
|---|---|
| One-off export | Run manually, hand over a file, done. |
| Ongoing refresh | Re-scrape on a cron, keep the table current, track additions/removals. |

**Recommendation:** start one-off; design the schema so an ongoing refresh
can be layered on later (see `05-storage-and-layout.md`). Needs manager
answer (open question 5).

## D2 — Catalog scope

### Manning
- Full catalog is publicly browsable (`/catalog`, `/books`, topic pages).
- Options: (a) entire catalog, (b) only "available now" / published (exclude
  MEAP early-access), (c) specific topics.
- **Recommendation:** entire published catalog; record MEAP status as a
  field rather than filtering, so scope stays simple.

### O'Reilly
- `https://www.oreilly.com/products/books-videos.html` is a **marketing
  landing page**, not a listing — it does not contain the catalog.
- The real catalog (search/browse) is largely gated behind an O'Reilly
  **learning subscription**.
- Options:
  - (a) Public subset only — O'Reilly-published titles exposed via
    `oreilly.com` sitemaps / the public library search without login
    (partial, mostly O'Reilly Media's own imprint).
  - (b) Full catalog via an authorized subscriber account (needs
    credentials + agreement it's allowed).
  - (c) Drop O'Reilly from this issue until access is sorted; ship Manning
    first.
- **Recommendation:** (c) or (a) depending on manager's answer to open
  question 3. Do not assume (b) without explicit authorization.

### Formats
- O'Reilly landing page mixes books, videos, live courses.
- Decide: books only, or books + video/course? **Recommendation:** books
  only for v1; add a `format` column so video can be included later without
  a schema change.
