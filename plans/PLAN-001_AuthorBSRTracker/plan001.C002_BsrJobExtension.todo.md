# PLAN-001 — C002: BSR Job Extension

← [plan001.main.md](plan001.main.md)

Extends `jobs/scrape_bsr.py` to read active books from the SQLite registry and adds the new `SMTP_*`, `EMAIL_TO`, `WEB_PORT`, `WEB_BASE_URL`, and `DB_PATH` config keys.

**Depends on:** [plan001.C001_AsinLookup.todo.md](plan001.C001_AsinLookup.todo.md)  
**Next →** [plan001.C003_EmailDigest.todo.md](plan001.C003_EmailDigest.todo.md)

---

## Config additions (`config.py`)

- [ ] Add `DB_PATH: str = "data/tracker.db"` to `Settings` — path to the SQLite file (relative to `WORKDIR`; Docker volume mounts `data/` there)
- [ ] Add `SMTP_HOST: str = "smtp.gmail.com"` to `Settings`
- [ ] Add `SMTP_PORT: int = 587`
- [ ] Add `SMTP_USER: str = ""`
- [ ] Add `SMTP_PASSWORD: str = ""`  (Gmail app password or SendGrid key)
- [ ] Add `EMAIL_FROM: str = ""`
- [ ] Add `EMAIL_TO: str = ""`  (fallback comma-separated for multiple recipients; overridden by per-book `email` from registry)
- [ ] Add `EMAIL_DIGEST_CRON: str = "0 8 * * *"`  (daily at 08:00 local time)
- [ ] Add `WEB_PORT: int = 8080`  (port the FastAPI registration UI listens on)
- [ ] Add `WEB_BASE_URL: str = "http://localhost:8080"`  (base URL prepended to unsubscribe links in emails; set to the public host when running in Docker)
- [ ] Add `@property email_recipients(self) -> list[str]` — split + strip `EMAIL_TO`
- [ ] Update `.env` (if present) with placeholder values for the new keys

---

## BSR job extension (`jobs/scrape_bsr.py`)

- [ ] Import `load_active_books` from `utils.registry`
- [ ] In `run()`: build the ASIN list as `tracked = [b["asin"] for b in load_active_books()]`
  - `load_active_books()` already filters `active=1` at the SQL level — no extra filter needed here
- [ ] Fall back to `settings.asins` when `tracked` is empty — keep backward-compat
- [ ] Log which source is used: `"Using SQLite registry (%d active ASINs)"` vs `"Using settings.TARGET_ASINS"`
- [ ] No other changes to scraping logic needed

---

## `main.py` — startup init

- [ ] Import `init_db` from `utils.registry`
- [ ] Call `init_db()` as the first statement in `main()` / startup — ensures `data/tracker.db` and table exist before any job or web handler runs
- [ ] Log `"SQLite registry initialised at <DB_PATH>"` at INFO

---

## Verification

- [ ] Ensure `data/tracker.db` has at least one active entry (from C001 verification)
- [ ] Run `python main.py` (or trigger BSR job directly); confirm `"Using SQLite registry"` is logged
- [ ] Confirm new snapshot files appear under `data/<ASIN>/`
- [ ] Delete `data/tracker.db` or run with an empty table; re-run; confirm fallback to `settings.asins` is logged
- [ ] `python -c "from config import settings; print(settings.SMTP_HOST, settings.WEB_PORT, settings.DB_PATH)"` — no import error
