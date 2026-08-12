# PLAN-001: Author BSR Tracker — Web UI Registration + Daily Email Digest

A lightweight tool that lets an author register their book via a Web UI (email, book title, profit %, current price), scrapes the Amazon Best Seller Rank daily, and emails a digest so they can track rank trends without opening a browser. The entire application runs as a single Docker container with a named volume for durable data storage.

---

## Ownership

Python-only, runs inside the existing `amazon-review-scraper` repo.  
Web UI served by **FastAPI + Jinja2** on a local port.  
Persistence via **SQLite** (`data/tracker.db`) — no external DB service needed.  
SMTP email sent directly from the scheduler job.  
Packaged as a **Docker image**; data directory mounted as a named Docker volume.

---

## Scope

| Module | Description |
|---|---|
| `web/app.py` | FastAPI app — serves the registration form, handles POST submissions, and unsubscribe routes |
| `web/templates/register.html` | Jinja2 HTML registration page — email, book title, profit %, current price |
| `web/templates/registered.html` | Confirmation page shown after successful registration |
| `web/templates/unsubscribe.html` | Unsubscribe confirmation page — shown after a book or email address is removed |
| `scripts/lookup_asin.py` | Helper called from the web handler — resolves ASIN from book title |
| `jobs/scrape_bsr.py` | Existing BSR scraper — extend to query active books from SQLite |
| `jobs/email_digest.py` | New job — reads latest BSR snapshots, builds HTML email, sends via SMTP |
| `config.py` | Add `SMTP_*`, `EMAIL_TO`, `WEB_PORT`, `WEB_BASE_URL`, and `DB_PATH` settings |
| `main.py` | Start FastAPI server + register `email_digest` cron job + call `init_db()` at startup |
| `utils/registry.py` | SQLite-backed registry: `init_db`, `register_book`, `load_active_books`, `unsubscribe_book`, `unsubscribe_email` |
| `templates/digest.html` | Jinja2 HTML email template (includes profit/price context + unsubscribe links) |
| `Dockerfile` | Multi-stage image — installs Python deps, copies app, exposes port |
| `docker-compose.yml` | Single-service compose file — mounts `bsr_data` named volume to `/app/data` |
| `.dockerignore` | Excludes `.venv`, `__pycache__`, `.env`, `*.pyc`, test files from image |

---

## Current behavior (baseline)

- `config.py` reads `TARGET_ASINS` — a hard-coded comma-separated env var.
- `jobs/scrape_bsr.py` loops over `settings.asins` and saves JSON snapshots under `data/<ASIN>/`.
- No Web UI exists.
- No email output exists.
- No title-to-ASIN resolution exists.

---

## Problems / gaps

1. Authors do not know their ASIN — they only know their book title.
2. ASINs are static in `.env`; there is no way to add a book at runtime.
3. Scraped data is never surfaced — only stored on disk.
4. No notification mechanism exists.
5. There is no way for an author to register their contact details or book economics (price, profit).

---

## Target outcomes

| Theme | Intent |
|---|---|
| Web UI onboarding | Author opens a browser, fills a form (email, title, profit %, price), clicks Register |
| ASIN auto-resolve | On form submit the server searches Amazon and resolves the ASIN transparently |
| Persistent tracking list | Tracked books survive container restarts via SQLite on a named Docker volume |
| Daily rank visibility | One email per day summarises current rank + 7-day trend + profit context per tracked book |
| Zero-config email | Works with any SMTP server (Gmail app password, SendGrid SMTP relay, etc.) |
| Containerised deployment | Single `docker compose up` starts the app; data lives on a named volume outside the image |

---

## Suggested layout

```
amazon-review-scraper/
├── web/
│   ├── app.py                   # new — FastAPI app + routes (register + unsubscribe)
│   └── templates/
│       ├── register.html        # new — registration form
│       ├── registered.html      # new — success/confirmation page
│       └── unsubscribe.html     # new — unsubscribe confirmation page
├── scripts/
│   └── lookup_asin.py           # new — ASIN lookup helper (used by web handler)
├── jobs/
│   ├── scrape_bsr.py            # extend — query SQLite for active books
│   └── email_digest.py          # new — build + send digest (with unsubscribe links)
├── utils/
│   └── registry.py              # new — SQLite registry (init_db, register_book, etc.)
├── templates/
│   └── digest.html              # new — Jinja2 email template
├── data/                        # mounted as Docker named volume (bsr_data → /app/data)
│   ├── tracker.db               # SQLite database (created by init_db at startup)
│   └── <ASIN>/                  # BSR snapshot JSON files (existing pattern)
├── Dockerfile                   # new — Docker image definition
├── docker-compose.yml           # new — single-service compose with named volume
├── .dockerignore                # new — excludes .venv, __pycache__, .env, etc.
└── config.py                    # extend — SMTP + WEB_PORT + WEB_BASE_URL + DB_PATH
```

---

## Implementation notes

- **Web UI** — FastAPI serves `GET /` (registration form) and `POST /register` (submit handler). Uses Jinja2 `TemplateResponse`. No JS framework needed — plain HTML form with Tailwind CDN for styling.
- **Registration flow** — `POST /register` receives `{email, title, profit_pct, current_price}`, calls `lookup_asin(title)` in a background thread, then calls `register_book(...)`. On success redirects to `/registered`.
- **ASIN lookup** — search Amazon via `https://www.amazon.com/s?k=<url-encoded-title>&i=stripbooks`; parse the first `[data-asin]` attribute. Use existing `utils/browser.py` (Playwright) to render the search results page.
- **SQLite registry** — lives in `utils/registry.py`. Uses Python's built-in `sqlite3` module — no new packages. Database file path is `settings.DB_PATH` (default `data/tracker.db`). `init_db()` creates the table with `IF NOT EXISTS` and is called at app startup. All writes use `with conn:` context manager for automatic commit/rollback. Thread-safe via `check_same_thread=False` + a module-level `threading.Lock`.
- **tracked_books table** — `(id INTEGER PRIMARY KEY, email TEXT, title TEXT, asin TEXT UNIQUE, profit_pct REAL, current_price REAL, added_at TEXT, active INTEGER DEFAULT 1)`. `active=1` is in-use; `active=0` is unsubscribed but retained for history.
- **Unsubscribe — single book** — `GET /unsubscribe?email=<email>&asin=<asin>` calls `unsubscribe_book(email, asin)` (sets `active=0`) and renders `unsubscribe.html` with `mode="book"`.
- **Unsubscribe — all books for an email** — `GET /unsubscribe?email=<email>` (no `asin`) calls `unsubscribe_email(email)` and renders `unsubscribe.html` with `mode="all"`.
- **Unsubscribe link in email** — each book row in `digest.html` contains a one-click link: `{WEB_BASE_URL}/unsubscribe?email=<email>&asin=<asin>`. A footer link covers the whole-address unsubscribe: `{WEB_BASE_URL}/unsubscribe?email=<email>`.
- **BSR extension** — `scrape_bsr.py` calls `load_active_books()` from `utils.registry`; filters `active=1` at the SQL level. Falls back to `settings.asins` when the query returns empty. Keeps backward-compat.
- **Email digest** — collect the most recent BSR snapshot per ASIN from `data/<ASIN>/` and up to 7 prior days for trend. Include `profit_pct` and `current_price` from the registry. Render with Jinja2. Send per unique email. Skip all records where `active=0`.
- **Docker** — single `python:3.12-slim` stage; installs Playwright deps + `requirements.txt`; sets `WORKDIR /app`; copies source; exposes `WEB_PORT`. The `data/` directory is **not** baked into the image — it is always provided by the named volume at runtime.
- **Named volume** — `docker-compose.yml` declares `bsr_data` volume and mounts it to `/app/data`. SQLite file and BSR snapshot folders both land inside this volume.
- **Environment variables in Docker** — all secrets (`SMTP_PASSWORD`, etc.) are passed via `env_file: .env` in `docker-compose.yml`; `.env` is listed in `.dockerignore`.
- **SMTP config** — stored in `.env`; never hard-coded.
- **No new pip packages** beyond `fastapi` and `uvicorn[standard]` — `sqlite3`, `smtplib`, `email`, and `Jinja2` are already available in the standard library / existing deps.

---

## Endpoint / data contract reference

### SQLite table `tracked_books` (inside `data/tracker.db`)

```sql
CREATE TABLE IF NOT EXISTS tracked_books (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    email        TEXT    NOT NULL,
    title        TEXT    NOT NULL,
    asin         TEXT    NOT NULL UNIQUE,
    profit_pct   REAL    NOT NULL,
    current_price REAL   NOT NULL,
    added_at     TEXT    NOT NULL,   -- ISO-8601 UTC
    active       INTEGER NOT NULL DEFAULT 1  -- 1 = tracking, 0 = unsubscribed
);
```

> `active = 0` means the record is retained for history but excluded from scraping and emails.

### Registration form fields

| Field | Type | Validation |
|---|---|---|
| `email` | `str` | valid email, required |
| `title` | `str` | non-empty, required |
| `profit_pct` | `float` | 0–100, required |
| `current_price` | `float` | > 0, required |

### BSR snapshot (existing, `data/<ASIN>/<timestamp>.json`)

```json
[
  {
    "asin": "0735211299",
    "rank": 1523,
    "category": "Books > Self-Help",
    "scraped_at": "2026-08-12T03:00:00+00:00"
  }
]
```

---

## Chapters

| Chapter | File | Focus | Status |
|---|---|---|---|
| C001 | `plan001.C001_AsinLookup.todo.md` | ASIN lookup helper + SQLite registry utilities | Not started |
| C002 | `plan001.C002_BsrJobExtension.todo.md` | Extend `scrape_bsr.py` + config settings | Not started |
| C003 | `plan001.C003_EmailDigest.todo.md` | `email_digest.py` job + Jinja2 template + SMTP config + unsubscribe links | Not started |
| C004 | `plan001.C004_WebUI.todo.md` | FastAPI web app — registration form + unsubscribe routes | Not started |
| C005 | `plan001.C005_Docker.todo.md` | Dockerfile + docker-compose.yml + named volume + .dockerignore | Not started |

---

## Files in this plan folder

| File | Purpose |
|---|---|
| `plan001.main.md` | This overview |
| `plan001.C001_AsinLookup.todo.md` | Chapter 1 tasks — ASIN lookup & SQLite registry |
| `plan001.C002_BsrJobExtension.todo.md` | Chapter 2 tasks — extend BSR scraper + config |
| `plan001.C003_EmailDigest.todo.md` | Chapter 3 tasks — email digest job |
| `plan001.C004_WebUI.todo.md` | Chapter 4 tasks — Web UI registration app |
| `plan001.C005_Docker.todo.md` | Chapter 5 tasks — Docker image + compose + volume |

---

## Done when

- [ ] Author opens `http://localhost:<WEB_PORT>`, fills the form (email, book title, profit %, current price), and clicks Register.
- [ ] The server resolves the ASIN, inserts the record into SQLite (`active=1`), and shows a confirmation page.
- [ ] The daily BSR cron job scrapes all **active** books queried from `data/tracker.db`.
- [ ] At the scheduled daily time each registered author receives an email with the current BSR, 7-day trend, and their book's profit context.
- [ ] Every book row in the email digest contains a one-click **"Unsubscribe this book"** link.
- [ ] The email footer contains a one-click **"Unsubscribe all"** link for the author's email address.
- [ ] Clicking either unsubscribe link opens a browser page confirming removal; the record is set to `active=0` in SQLite.
- [ ] After unsubscribing, the author no longer receives emails for the removed book(s) and the BSR job skips them.
- [ ] `docker compose up` starts the container; the Web UI is reachable at `http://localhost:<WEB_PORT>`.
- [ ] All data (SQLite DB + BSR snapshots) persists in the `bsr_data` named volume across container restarts and image rebuilds.
