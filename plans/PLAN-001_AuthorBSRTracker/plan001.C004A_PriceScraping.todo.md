# PLAN-001 — C004A: Daily Price Scraping

← [plan001.main.md](plan001.main.md)

Removes the manual **Current price ($)** field from the registration form. Price is scraped from the Amazon product page **on every BSR scrape run** and stored in `bsr_snapshots` alongside the rank. The email digest reads the latest price from the snapshot, not from `tracked_books`.

**Depends on:** [plan001.C004_WebUI.todo.md](plan001.C004_WebUI.todo.md), [plan001.C002_BsrJobExtension.todo.md](plan001.C002_BsrJobExtension.todo.md)

---

## `jobs/scrape_bsr.py` — scrape price alongside BSR

- [x] Add `price: float` field to `BestSellerRank` dataclass (default `0.0`)
- [x] In `_scrape_bsr(asin)`, after fetching `html`, inline price parsing:
  - Try selectors in priority order on the already-fetched `soup`:
    1. `span.a-offscreen`
    2. `span#price_inside_buybox`
    3. `span#kindle-price`
    4. `span.a-color-price`
  - Strip `$`, `,`, whitespace; cast to `float`; default to `0.0` if no match or parse fails
  - Log at INFO: `"scrape_bsr: ASIN %s price → $%.2f"` (or `"price not found"` at WARNING)
  - Attach the parsed price to every `BestSellerRank` row for this ASIN
- [x] No extra HTTP request — price extraction reuses the product page HTML already loaded for BSR

---

## `utils/registry.py` — add `price` column to `bsr_snapshots`

- [x] Add `price REAL NOT NULL DEFAULT 0` to `_CREATE_BSR_SNAPSHOTS_TABLE`:
  ```sql
  CREATE TABLE IF NOT EXISTS bsr_snapshots (
      id         INTEGER PRIMARY KEY AUTOINCREMENT,
      asin       TEXT    NOT NULL,
      rank       INTEGER NOT NULL,
      category   TEXT    NOT NULL,
      price      REAL    NOT NULL DEFAULT 0,
      scraped_at TEXT    NOT NULL
  );
  ```
- [x] Update `_BsrRecord` Protocol: add `price: float`
- [x] Update `save_bsr_snapshots()`:
  - Row tuple: `(r.asin, r.rank, r.category, r.price, r.scraped_at)`
  - INSERT: `(asin, rank, category, price, scraped_at)`
- [x] Update `load_latest_snapshot()`: include `price` in the SELECT
- [x] **Migration** — existing `tracker.db` lacks the `price` column; add an `ALTER TABLE` guard in `init_db()`:
  ```python
  try:
      conn.execute("ALTER TABLE bsr_snapshots ADD COLUMN price REAL NOT NULL DEFAULT 0")
  except sqlite3.OperationalError:
      pass  # column already exists
  ```
- [x] `tracked_books.current_price` column is **kept** for backward compatibility but no longer updated after registration; email digest reads price from `bsr_snapshots` instead

---

## `web/app.py` — remove price form field

- [x] Remove `current_price: str = Form(...)` parameter from `POST /register`
- [x] Remove `price_val` validation block (`try: price_val = float(current_price) ...`)
- [x] Remove `current_price=current_price` from the `bad()` helper kwargs
- [x] Pass `current_price=0.0` as seed value in `repo.register_book({...})` (price will be populated on first scrape)

---

## `web/templates/register.html` — remove price input

- [x] Delete the `<label>` + `<input type="number" name="current_price" ...>` block
- [x] Remove any `value="{{ current_price }}"` re-fill attribute
- [x] Add a small grey note below the profit % field:
  > "Book price is fetched automatically from Amazon each day."

---

## `jobs/email_digest.py` — read price from latest snapshot

- [x] When building each book's context dict, read `price` from `load_latest_snapshot(asin)` instead of `tracked_books.current_price`
- [x] Fall back to `tracked_books.current_price` (seed value `0.0`) if no snapshot exists yet

---

## Verification

- [ ] Submit the registration form (no price field) — confirm `data/tracker.db` row has `current_price = 0.0`
- [ ] Trigger `scrape_bsr.run()` manually — confirm `bsr_snapshots` rows have a non-zero `price` value
- [ ] Inspect logs — confirm `"scrape_bsr: ASIN ... price → $..."` line (or `"price not found"`) appears per ASIN
- [ ] Trigger scrape on an ASIN with no parseable price — confirm scrape still saves BSR rows with `price = 0.0`, no crash
- [ ] Trigger email digest — confirm price shown in email comes from the latest snapshot, not the seed `0.0` in `tracked_books`
- [ ] Apply migration: delete `price` column from a test DB and re-run `init_db()` — confirm column is added without error
