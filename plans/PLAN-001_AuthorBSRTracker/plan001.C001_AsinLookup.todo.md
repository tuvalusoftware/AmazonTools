# PLAN-001 — C001: ASIN Lookup & SQLite Registry

← [plan001.main.md](plan001.main.md)

Delivers `scripts/lookup_asin.py` (lookup helper used by the Web UI handler) and `utils/registry.py` (SQLite-backed book registry). The registry stores author contact and economics: `email`, `profit_pct`, and `current_price` alongside `title`, `asin`, and an `active` flag.

**Next →** [plan001.C002_BsrJobExtension.todo.md](plan001.C002_BsrJobExtension.todo.md)

---

## Setup

- [ ] Create `scripts/` folder if it does not exist; add `scripts/__init__.py` (empty)
- [ ] Confirm `playwright` browsers are installed (`playwright install chromium`)
- [ ] Add `fastapi` and `uvicorn[standard]` to `requirements.txt` (used by C004 Web UI)
- [ ] Ensure `utils/` folder exists; add `utils/registry.py` (new file)

---

## `utils/registry.py` — SQLite registry

### DB connection helper
- [ ] Import `sqlite3`, `threading`, `pathlib.Path`, `datetime`, `config.settings`
- [ ] Define `DB_PATH = Path(settings.DB_PATH)` — resolved at import time
- [ ] Create a module-level `_lock = threading.Lock()` for write serialisation
- [ ] Write `_get_conn() -> sqlite3.Connection`
  - Opens `sqlite3.connect(str(DB_PATH), check_same_thread=False)`
  - Sets `conn.row_factory = sqlite3.Row` for dict-like access
  - Returns the connection (caller is responsible for closing)

### Schema initialisation
- [ ] Write `init_db() -> None`
  - Creates parent directories for `DB_PATH` with `mkdir(parents=True, exist_ok=True)`
  - Executes `CREATE TABLE IF NOT EXISTS tracked_books` with columns:
    ```
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL,
    title         TEXT NOT NULL,
    asin          TEXT NOT NULL UNIQUE,
    profit_pct    REAL NOT NULL,
    current_price REAL NOT NULL,
    added_at      TEXT NOT NULL,
    active        INTEGER NOT NULL DEFAULT 1
    ```
  - Called once at app startup (`main.py`) before any other registry function

### Registry helpers
- [ ] Write `register_book(book: dict) -> bool`
  - Expected keys: `email`, `title`, `asin`, `profit_pct`, `current_price`
  - Under `_lock`: try `INSERT INTO tracked_books … VALUES (…)` with `added_at = utcnow().isoformat()`
  - On `sqlite3.IntegrityError` (UNIQUE on `asin`): check if existing row has `active=0`; if so, run `UPDATE … SET active=1` and return `True` (reactivation); if already `active=1` return `False` (duplicate)
  - Returns `True` when newly inserted or reactivated, `False` when already active duplicate
- [ ] Write `load_active_books() -> list[dict]`
  - `SELECT * FROM tracked_books WHERE active = 1`
  - Returns list of plain dicts (use `[dict(row) for row in cursor.fetchall()]`)
- [ ] Write `unsubscribe_book(email: str, asin: str) -> bool`
  - Under `_lock`: `UPDATE tracked_books SET active=0 WHERE email=? AND asin=? AND active=1`
  - Returns `True` if `cursor.rowcount > 0`, else `False`
- [ ] Write `unsubscribe_email(email: str) -> int`
  - Under `_lock`: `UPDATE tracked_books SET active=0 WHERE email=? AND active=1`
  - Returns `cursor.rowcount` (number of records deactivated)
- [ ] Export all four helpers + `init_db` from `utils/__init__.py`

---

## `scripts/lookup_asin.py` — ASIN lookup helper

- [ ] Create `scripts/lookup_asin.py`
- [ ] Import `utils.registry` functions for use by Web UI handler

### Amazon search helper
- [ ] Write `search_asin(title: str) -> tuple[str, str]`
  - Import `utils.browser.fetch_page_html` to fetch the rendered search results page
  - Build search URL: `https://www.amazon.com/s?k=<urllib.parse.quote_plus(title)>&i=stripbooks`
  - Parse the HTML with `BeautifulSoup`; collect **all** `[data-asin]` attributes on search result `div`s that have a non-empty `data-asin` value
  - **Always use the first candidate** — Amazon returns results sorted by relevance; no disambiguation UI is shown
  - Return `(title, asin)` using that first candidate, or raise `ValueError("ASIN not found")` if the list is empty
  - Log the resolved ASIN and how many candidates were found at INFO level using `utils.logger.get_logger`

---

## Registry record schema (SQL)

```sql
-- active=1: currently tracked
-- active=0: unsubscribed (retained for history)
INSERT INTO tracked_books (email, title, asin, profit_pct, current_price, added_at, active)
VALUES ('author@example.com', 'Atomic Habits', '0735211299', 70.0, 14.99, '2026-08-12T03:00:00+00:00', 1);
```

---

## Verification

- [ ] Run `python -c "from utils.registry import init_db; init_db()"` — confirm `data/tracker.db` created
- [ ] Call `search_asin("Atomic Habits")` from a Python shell — confirm ASIN printed
- [ ] Call `register_book({"email": "me@test.com", "title": "Atomic Habits", "asin": "<asin>", "profit_pct": 70.0, "current_price": 14.99})` — confirm returns `True`
- [ ] Query `data/tracker.db` with `sqlite3` CLI — confirm row has `active=1`
- [ ] Call `register_book` again with the same ASIN — confirm returns `False` (active duplicate)
- [ ] Call `unsubscribe_book("me@test.com", "<asin>")` — confirm returns `True`; row now `active=0`
- [ ] Call `register_book` again after unsubscribe — confirm returns `True` (reactivation)
- [ ] Call `unsubscribe_email("me@test.com")` — confirm returns count > 0; all rows for email are `active=0`
- [ ] Call `load_active_books()` after full unsubscribe — confirm returns `[]`
- [ ] Check no new packages were pulled into `.venv` beyond `fastapi` and `uvicorn`
