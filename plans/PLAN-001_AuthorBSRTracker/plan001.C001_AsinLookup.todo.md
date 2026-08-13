# PLAN-001 — C001: ASIN Lookup & SQLite Registry

← [plan001.main.md](plan001.main.md)

Delivers `scripts/lookup_asin.py` (lookup helper used by the Web UI handler) and `utils/registry.py` (SQLite-backed book registry). The registry stores author contact and economics: `email`, `profit_pct`, and `current_price` alongside `title`, `asin`, and an `active` flag.

**Next →** [plan001.C002_BsrJobExtension.todo.md](plan001.C002_BsrJobExtension.todo.md)

---

## Setup

- [x] Create `scripts/` folder if it does not exist; add `scripts/__init__.py` (empty)
- [ ] Confirm `playwright` browsers are installed (`playwright install chromium`)
- [x] Add `fastapi` and `uvicorn[standard]` to `requirements.txt` (used by C004 Web UI)
- [x] Ensure `utils/` folder exists; add `utils/registry.py` (new file)

---

## `utils/registry.py` — SQLite registry

### `BookRepo` class
- [x] Define `class BookRepo` — thread-safe SQLite repository for tracked books
- [x] `__init__(self, db_path: str | Path | None = None)` — accepts optional path, defaults to `settings.DB_PATH`; stores `self._db_path` and `self._lock = threading.Lock()`
- [x] `_get_conn(self) -> sqlite3.Connection` — opens connection with `check_same_thread=False`, sets `row_factory = sqlite3.Row`

### Schema initialisation
- [x] `BookRepo.init_db(self) -> None`
  - Creates parent directories for `_db_path` with `mkdir(parents=True, exist_ok=True)`
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
  - Called once at app startup (`main.py`) before any other registry method

### Write methods
- [x] `BookRepo.register_book(self, book: dict) -> bool`
  - Expected keys: `email`, `title`, `asin`, `profit_pct`, `current_price`
  - Under `self._lock`: try `INSERT INTO tracked_books … VALUES (…)` with `added_at = utcnow().isoformat()`
  - On `sqlite3.IntegrityError` (UNIQUE on `asin`): check if existing row has `active=0`; if so, run `UPDATE … SET active=1` and return `True` (reactivation); if already `active=1` return `False` (duplicate)
  - Returns `True` when newly inserted or reactivated, `False` when already active duplicate
- [x] `BookRepo.unsubscribe_book(self, email: str, asin: str) -> bool`
  - Under `self._lock`: `UPDATE tracked_books SET active=0 WHERE email=? AND asin=? AND active=1`
  - Returns `True` if `cursor.rowcount > 0`, else `False`
- [x] `BookRepo.unsubscribe_email(self, email: str) -> int`
  - Under `self._lock`: `UPDATE tracked_books SET active=0 WHERE email=? AND active=1`
  - Returns `cursor.rowcount` (number of records deactivated)

### Read methods
- [x] `BookRepo.load_active_books(self) -> list[dict]`
  - `SELECT * FROM tracked_books WHERE active = 1`
  - Returns list of plain dicts (use `[dict(row) for row in cursor.fetchall()]`)

### Module-level export
- [x] Export `BookRepo` from `utils/__init__.py`

---

## `scripts/lookup_asin.py` — ASIN lookup helper

- [x] Create `scripts/lookup_asin.py`
- [x] Import `utils.registry` functions for use by Web UI handler

### Amazon search helper
- [x] Write `search_asin(title: str) -> tuple[str, str]`
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

- [x] Run `python -c "from utils.registry import init_db; init_db()"` — confirm `data/tracker.db` created
- [ ] Call `search_asin("Atomic Habits")` from a Python shell — confirm ASIN printed
- [x] Call `BookRepo().register_book({"email": "me@test.com", "title": "Atomic Habits", "asin": "<asin>", "profit_pct": 70.0, "current_price": 14.99})` — confirm returns `True`
- [x] Query `data/tracker.db` with `sqlite3` CLI — confirm row has `active=1`
- [x] Call `register_book` again with the same ASIN — confirm returns `False` (active duplicate)
- [x] Call `unsubscribe_book("me@test.com", "<asin>")` — confirm returns `True`; row now `active=0`
- [x] Call `register_book` again after unsubscribe — confirm returns `True` (reactivation)
- [x] Call `unsubscribe_email("me@test.com")` — confirm returns count > 0; all rows for email are `active=0`
- [x] Call `load_active_books()` after full unsubscribe — confirm returns `[]`
- [x] Check no new packages were pulled into `.venv` beyond `fastapi` and `uvicorn`
