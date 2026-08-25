# Amazon BSR & Price Tracker

A self-hosted tool that periodically tracks Amazon Best Seller Rank (BSR) and
price for a list of books/products, stores snapshots in SQLite, and emails
subscribers a digest with PDF charts. Includes a small FastAPI web UI for
readers to register/unsubscribe from the digest.

## Tech stack

| Layer | Library |
|---|---|
| Scheduler | [APScheduler](https://apscheduler.readthedocs.io/) |
| Browser automation | [Playwright](https://playwright.dev/python/) (persisted login session) |
| BSR extraction | [ScrapeGraphAI](https://github.com/ScrapeGraphAI/Scrapegraph-ai) `SmartScraperGraph` (LLM-based; provider set by `LLM_PROVIDER`) |
| Web UI | FastAPI + Uvicorn |
| Storage | SQLite (via `utils/registry.py` repo classes) |
| Email templating | Jinja2 |
| PDF charts | matplotlib |
| Config / env | pydantic-settings |

## Project structure

```
amazon-review-scraper/
├── main.py                    # Entry point — starts the APScheduler loop + FastAPI web UI
├── config.py                  # All settings (loaded from .env), LLM graph_config builder
├── jobs/
│   ├── scrape_bsr.py          # Cron job: fetch price/BSR per ASIN → save snapshot
│   ├── email_digest.py        # Cron job: build + send the BSR digest email
│   └── monthly_summary.py     # Cron job: precompute monthly profit summary
├── web/
│   ├── app.py                 # FastAPI app: register / unsubscribe pages
│   └── templates/             # Jinja2 templates for the web UI
├── utils/
│   ├── browser.py             # Playwright login/session helpers
│   ├── registry.py            # BookRepo — active books registry
│   ├── Repo_Snapshot.py       # BSR/price snapshot repo
│   ├── Repo_CronRunLog.py     # Cron run logging repo
│   ├── Repo_MonthlySummary.py # Monthly profit summary repo
│   ├── Formula_calculator.py  # Profit/royalty calculations
│   ├── logger.py              # Rotating file + stdout logger
│   └── storage.py             # JSON / CSV writer
├── scripts/                   # One-off/interactive helpers (ASIN lookup, run-job picker, reset-db)
├── templates/digest.html      # Email digest HTML template
├── reports/                   # PDF report generation (charts via matplotlib)
├── data/                      # SQLite DB, browser session, snapshots (auto-created)
├── logs/                      # Log files (auto-created)
├── docs/, issues/             # Design docs and issue plans
├── docker-compose.yml, Dockerfile
├── requirements.txt
└── .env.example
```

## Quick start

```bash
# 1. Clone / enter the project
cd amazon-review-scraper

# 2. Install (creates venv, installs deps, installs Playwright browsers)
make install

# 3. Configure
cp .env.example .env
# Edit .env — set TARGET_ASINS, LLM_PROVIDER (+ its API key), SMTP__* at minimum

# 4. Log in to Amazon once (opens a visible browser for OTP/CAPTCHA,
#    saves the session to data/browser_state.json)
make login

# 5. Run the app (scheduler + web UI)
make start
```

## Commands

- `make install` — create venv, install deps, `playwright install`
- `make start` — run the full app (scheduler + web UI), same as `python main.py`
- `make run` — run the BSR scrape job directly, once
- `make run-job` — interactively pick which job to run on demand (scrape, digest, or both)
- `make login` — interactive Amazon login (opens a visible browser for OTP/CAPTCHA), saves session to `data/browser_state.json`
- `make test` — unit tests (`pytest -m "not integration"`, no network/session required)
- `make test-integration` — hits live Amazon; **requires `make login` first**
- `make reset-db -- --yes` — drop and re-create all tables (destructive, requires explicit confirmation)

## Scraping

- Amazon access uses a **persisted Playwright browser session** (`data/browser_state.json`), not plain HTTP requests. Run `make login` before first use or after the session expires.
- Price is parsed directly from the DOM. BSR rank/category is extracted via an LLM (`SmartScraperGraph`) fed only a small HTML fragment — not the full page — to save tokens. Only top-level `"Kindle Store"` / `"Audible Books & Originals"` categories are kept; sub-category ranks are discarded.
- CAPTCHA/robot-check detection saves screenshots to `data/captcha/` and `data/debug/`, and the fetch retries with exponential backoff (`SCRAPE_RETRIES`, `SCRAPE_RETRY_DELAY`).

## Scheduled jobs

| Job | Config | Purpose |
|---|---|---|
| `scrape_bsr` | `SCRAPE_BSR_CRON` (default `0 23 * * *`) | Fetch price/BSR per ASIN, save a snapshot |
| `email_digest` | `EMAIL_DIGEST_CRON` (default weekly, Mon 01:00) | Send the BSR digest email (HTML + PDF) to registered subscribers |
| `monthly_summary` | `MONTHLY_SUMMARY_CRON` (default `5 0 1 * *`) | Precompute the monthly profit summary; includes self-healing backfill for missed runs |

All cron expressions are interpreted against `TIMEZONE`. Each run is logged to the cron run log table.

## Configuration

All options live in `.env` (see `.env.example`). Key groups:

| Group | Variables |
|---|---|
| Scheduler | `SCRAPE_BSR_CRON`, `EMAIL_DIGEST_CRON`, `MONTHLY_SUMMARY_CRON`, `TIMEZONE` |
| Scrape targets | `TARGET_ASINS` (comma-separated), `AMAZON_PRODUCT_URL`, `SCRAPE_RETRIES`, `SCRAPE_RETRY_DELAY`, `REQUEST_DELAY` |
| LLM (BSR extraction) | `LLM_PROVIDER` (`ollama` \| `openai` \| `groq` \| `gemini`) + matching API key/model vars, `LLM_VERBOSE` |
| Browser | `BROWSER_HEADLESS`, `BROWSER_STATE_PATH`, `AMAZON_EMAIL`/`AMAZON_PASSWORD` (used by auto-login) |
| Storage | `DB_PATH` (SQLite), `OUTPUT_DIR`, `OUTPUT_FORMAT` |
| Email / SMTP | `SMTP__HOST`, `SMTP__PORT`, `SMTP__USER`, `SMTP__PASSWORD` (Gmail App Password), `SMTP__FROM_ADDR` |
| Web UI | `WEB_PORT`, `WEB_BASE_URL` |
| Logging | `LOG_LEVEL`, `LOG_DIR` |

> `WEB_BASE_URL` must be a host-reachable address (not `localhost`) since it's embedded in email unsubscribe links — especially easy to get wrong under Docker.

## Web UI

FastAPI app (`web/app.py`) mounted alongside the scheduler on `WEB_PORT`:

- `GET /` — landing/registration page
- `POST /register` — register an email for the BSR digest
- `GET /registered` — confirmation page
- `GET /unsubscribe` — unsubscribe via the link sent in digest emails

## Docker

```bash
docker compose up -d --build
```

Uses `docker-compose.yml` / `Dockerfile`. The `bsr_data` volume persists the SQLite DB (`tracker.db`) and BSR snapshot folders across restarts and rebuilds. Requires a valid `.env` (see Configuration) — note the `WEB_BASE_URL` caveat above.
