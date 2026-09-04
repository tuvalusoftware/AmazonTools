# 3. BSR/price scrape run — verify data lands in SQLite

Precondition: [02-register-flow.md](./02-register-flow.md) happy path done —
at least one row with `active = 1` in `tracked_books`, and you have its
`asin` noted.

Do this in a **second terminal**, separate from the one running `make
start`, so the running app (and its scheduler) is untouched.

## Trigger a scrape manually

- [ ] Run `make run-job` and choose option **1) Scrape BSR/price job** when
      prompted (`scripts/run_job.py` runs `jobs.scrape_bsr.run()` — same job
      the cron scheduler would fire, but on demand).
  - Expected log lines: `=== scrape_bsr job started ===`, `Using SQLite
    registry (N active ASINs)`, `Scraping BSR for ASIN: <your asin>`,
    `ASIN <asin> → M rank entries`, `=== scrape_bsr job finished — total
    saved: M ===`.
  - Approx wait time: real Amazon page load + LLM extraction per book, a
    few seconds to ~1 minute depending on retries.

## Verify persistence

- [ ] Inspect the snapshot table:
      `sqlite3 data/tracker.db "SELECT asin, rank, category, price, scraped_at FROM bsr_snapshots WHERE asin = '<your asin>' ORDER BY scraped_at DESC;"`
  - Expected: at least one new row for your `asin`.
  - `rank` is a positive integer.
  - `category` is exactly `Kindle Store` or `Audible Books & Originals`
    (sub-category ranks are intentionally discarded — see `claude.md`
    "Scraping" section).
  - `price` is a non-negative number. If it's `0.0`, that's a known soft
    failure mode (Amazon's price selector can miss) — note it but don't
    treat it as a blocking bug on its own; re-run once to confirm it's not
    consistently `0`.

## Retry/CAPTCHA check (only if the scrape produced 0 entries)

- [ ] If the log shows `ASIN <asin> — no BSR data found` after all retries
      are exhausted, check `data/captcha/` and `data/debug/` for a fresh
      screenshot.
  - If a CAPTCHA screenshot appears: your Amazon session likely needs a
    fresh `make login` — this is an environment issue, not an app bug.
  - If no CAPTCHA but still 0 entries: note the ASIN and screenshot as a
    potential bug (LLM prompt/selector may need updating).

## Multiple books (optional, recommended once)

- [ ] Register a second book (repeat [02-register-flow.md](./02-register-flow.md)
      happy path with a different title/ASIN, same or different email).
- [ ] Run `make run-job` again, choosing option **1** once more.
  - Expected: both ASINs are scraped in the same run, with a
    `settings.REQUEST_DELAY`-second pause between them (log line "Waiting
    N.Ns before next ASIN …").
  - Verify both ASINs now have rows in `bsr_snapshots`.
