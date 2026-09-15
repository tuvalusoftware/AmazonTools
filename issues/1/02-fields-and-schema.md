# 3. Fields & schema

## Confirmed by the request
- `title`
- `author` (one or more)
- `category` (one or more, per site taxonomy)

## Candidate extra fields — decide which to keep

| Field | Keep? | Why it may matter |
|---|---|---|
| `publisher` | yes | needed to tell Manning vs O'Reilly rows apart in one table |
| `product_url` | yes | canonical identity, lets a human verify a row |
| `isbn` / `isbn13` | recommend yes | best dedup / cross-reference key; also bridges to Amazon lookup (D1 option B) |
| `format` | recommend yes | print / ebook / video / audio; needed if formats get mixed |
| `price` | optional | changes over time; only if the manager wants it |
| `publication_date` | optional | useful for "new releases" filtering |
| `page_count` | no | low value for this dataset |
| `description` | optional | large text; only if needed downstream |
| `cover_image_url` | optional | only if the delivery format shows covers |
| `meap` / `early_access` | Manning only | whether the book is finished |
| `scraped_at` | yes | provenance / refresh tracking |

**Recommendation:** `publisher, title, author, category, product_url, isbn13,
format, publication_date, scraped_at`. Everything else deferred.

## Multiple authors
- Options: (a) single joined string `"A. Smith, B. Jones"`, (b) a separate
  `book_authors` child table, (c) JSON array column.
- **Recommendation:** (a) joined string for v1 — matches the flat, plain
  columns style used by `book_monthly_summary` / `cron_run_log`. Revisit
  only if a downstream consumer needs per-author queries.

## Multiple categories
- Each site has its own taxonomy (Manning topic tags; O'Reilly topics).
- Options: (a) store the site's raw primary category string as-is,
  (b) store all category strings joined, (c) map both sites onto a common
  in-house taxonomy.
- **Recommendation:** (b) store the raw category path(s) exactly as shown,
  joined — same approach the BSR job already takes (`category` string "as
  shown"). No taxonomy mapping in this issue.

## Dedup / primary key
- Options: `isbn13`, `product_url`, or `(publisher, title, author)`.
- `isbn13` is cleanest but not always shown on listing pages (may need the
  detail page).
- **Recommendation:** primary dedup on `product_url` (always available),
  with `isbn13` as a secondary unique index when present. Upsert on
  `product_url`, same write-once-then-upsert pattern as
  `MonthlySummaryRepo`.
