# PLAN-001 — C002: BSR Job Extension

← [plan001.main.md](plan001.main.md)

Extends `jobs/scrape_bsr.py` to read active books from the SQLite registry and adds the new `smtp.*`, `EMAIL_TO`, `WEB_PORT`, `WEB_BASE_URL`, and `DB_PATH` config keys.

**Depends on:** [plan001.C001_AsinLookup.todo.md](plan001.C001_AsinLookup.todo.md)  
**Next →** [plan001.C003_EmailDigest.todo.md](plan001.C003_EmailDigest.todo.md)

---

## Config additions (`config.py`)

- [x] Add `DB_PATH: str = "data/tracker.db"` to `Settings` — path to the SQLite file (relative to `WORKDIR`; Docker volume mounts `data/` there)
- [x] Add `SmtpSettings(BaseModel)` nested model with fields:
  - `host: str = "smtp.gmail.com"`
  - `port: int = 587`
  - `user: str = ""`
  - `password: str = ""` (Gmail app password or SendGrid key)
  - `from_addr: str = ""`
- [x] Add `smtp: SmtpSettings = SmtpSettings()` field to `Settings`
  - Set via `.env` / env vars using double-underscore delimiter: `SMTP__HOST`, `SMTP__USER`, `SMTP__PASSWORD`, `SMTP__FROM_ADDR`
  - Requires `env_nested_delimiter="__"` in `model_config` ← **already added**
- [x] Add `EMAIL_TO: str = ""` (fallback comma-separated for multiple recipients; overridden by per-book `email` from registry)
- [x] Add `EMAIL_DIGEST_CRON: str = "0 8 * * *"` (daily at 08:00 local time)
- [x] Add `WEB_PORT: int = 8080` (port the FastAPI registration UI listens on)
- [x] Add `WEB_BASE_URL: str = "http://localhost:8080"` (base URL prepended to unsubscribe links in emails; set to the public host when running in Docker)
- [x] Add `@property email_recipients(self) -> list[str]` — split + strip `EMAIL_TO`
- [x] Update `.env` (if present) with placeholder values for the new keys:
  ```
  SMTP__HOST=smtp.gmail.com
  SMTP__PORT=587
  SMTP__USER=
  SMTP__PASSWORD=
  SMTP__FROM_ADDR=
  EMAIL_TO=
  EMAIL_DIGEST_CRON=0 8 * * *
  WEB_PORT=8080
  WEB_BASE_URL=http://localhost:8080
  ```

---

## BSR job extension (`jobs/scrape_bsr.py`)

- [x] Import `load_active_books` from `utils.registry`
- [x] In `run()`: build the ASIN list as `tracked = [b["asin"] for b in load_active_books()]`
  - `load_active_books()` already filters `active=1` at the SQL level — no extra filter needed here
- [x] If `tracked` is empty → log `"No active ASINs in registry — skipping run"` and return immediately; no fallback
- [x] Remove all references to `settings.asins` / `settings.TARGET_ASINS` from the job
- [x] Log `"Using SQLite registry (%d active ASINs)"` when proceeding
- [x] Replace `save_results(asin, ranks)` call with `BookRepo().save_bsr_snapshots(ranks)` — insert each `BestSellerRank` as a row in `bsr_snapshots`
- [x] Remove `from utils.storage import save_results` import
- [x] Remove `total_saved` counter (or recount from `save_bsr_snapshots` return value)

---

## `utils/registry.py` — bsr_snapshots table

- [x] Add `_CREATE_BSR_SNAPSHOTS_TABLE` SQL string:
  ```sql
  CREATE TABLE IF NOT EXISTS bsr_snapshots (
      id         INTEGER PRIMARY KEY AUTOINCREMENT,
      asin       TEXT    NOT NULL,
      rank       INTEGER NOT NULL,
      category   TEXT    NOT NULL,
      scraped_at TEXT    NOT NULL
  );
  CREATE INDEX IF NOT EXISTS idx_bsr_snapshots_asin_scraped
      ON bsr_snapshots (asin, scraped_at DESC);
  ```
- [x] In `init_db()`: execute `_CREATE_BSR_SNAPSHOTS_TABLE` after `_CREATE_TABLE`
- [x] Add `save_bsr_snapshots(self, records: list) -> int` method to `BookRepo`:
  - Accepts a `list[BestSellerRank]` (or any objects with `.asin`, `.rank`, `.category`, `.scraped_at`)
  - Uses `executemany` to insert all rows in a single transaction
  - Returns count of rows inserted

---

## `main.py` — startup init

- [x] Import `init_db` from `utils.registry`
- [x] Call `init_db()` as the first statement in `main()` / startup — ensures `data/tracker.db` and table exist before any job or web handler runs
- [x] Log `"SQLite registry initialised at <DB_PATH>"` at INFO

---

## Verification

- [x] Ensure `data/tracker.db` has at least one active entry (from C001 verification)
- [ ] Confirm new rows appear in `bsr_snapshots` table: `sqlite3 data/tracker.db "SELECT * FROM bsr_snapshots LIMIT 5;"`
- [ ] Confirm **no** `data/<ASIN>/` directories are created
- [ ] Delete `data/tracker.db` or run with an empty table; re-run; confirm `"No active ASINs in registry — skipping run"` is logged and job exits cleanly
- [ ] `python -c "from config import settings; print(settings.smtp.host, settings.WEB_PORT, settings.DB_PATH)"` — no import error
