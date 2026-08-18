# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> Note: `README.md` describes an earlier "review scraper" concept and does not reflect the current app (Amazon BSR/price tracker with email digest, PDF reports, and a web UI). Don't treat it as authoritative.

# Project conventions for Claude

## Python — repository / service classes

- **Always call class methods directly** on an instance of the class (e.g. `BookRepo().load_active_books()`).
- Do **not** wrap class methods in module-level helper functions just to shorten the call site.
- If a caller needs a shared instance, let it create and hold its own (or receive one via dependency injection) — do not create a module-level singleton in the library module.

## Commands

- `make install` — create venv, install deps, `playwright install`
- `make start` / `make run` — run the web app / run the scrape job directly
- `make login` — interactive Amazon login (opens a visible browser for OTP/CAPTCHA), saves session to `data/browser_state.json`
- `make test` — unit tests (`pytest -m "not integration"`)
- `make test-integration` — hits live Amazon; **requires `make login` first**, or it will fail

## Scraping

- Amazon access uses a **persisted Playwright browser session** (`data/browser_state.json`), not plain HTTP requests. Run `make login` before first use or after the session expires.
- Price is parsed directly from the DOM. BSR rank/category is extracted via an LLM (SmartScraperGraph, provider set by `LLM_PROVIDER`) fed only a small HTML fragment — not the full page — to save tokens. Only top-level `"Kindle Store"` / `"Audible Books & Originals"` categories are kept; sub-category ranks are discarded.
- CAPTCHA/robot-check detection saves screenshots to `data/captcha/` and `data/debug/`, and the fetch retries with exponential backoff (`SCRAPE_RETRIES`, `SCRAPE_RETRY_DELAY`).

## Configuration

- Settings come from `.env` (see `.env.example`) via pydantic-settings — SQLite path (`DB_PATH`), SMTP (Gmail App Password required), `LLM_PROVIDER` + per-provider API keys, `CRON_SCHEDULE`/`EMAIL_DIGEST_CRON`.
- `WEB_BASE_URL` must be a host-reachable address (not `localhost`) since it's embedded in email unsubscribe links — especially easy to get wrong under Docker.
