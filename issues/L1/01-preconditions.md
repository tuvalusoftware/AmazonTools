# 1. Preconditions & environment setup

Tick each item before starting the flows in the other checklists. If any
item fails, stop and fix it first — later steps assume all of these hold.

## Environment

- [x] `.env` exists (copied from `.env.example`) with real values for:
  - [x] `LLM_PROVIDER` + matching API key (e.g. `GOOGLE_API_KEY` for
    ```
    `gemini`) — used to extract BSR from the scraped HTML fragment.
    ```
  - [x] `DB_PATH` (default `data/tracker.db`) — note this path; step 3 will
    ```
    inspect this file directly.
    ```
  - [x] `SMTP__HOST` / `SMTP__PORT` / `SMTP__USER` / `SMTP__PASSWORD` /
    ```
    `SMTP__FROM_ADDR` — Gmail App Password, not the normal account
    password.
    ```
  - [x] `WEB_PORT` (default `8080`).
  - [x] `CRON_SCHEDULE` / `EMAIL_DIGEST_CRON` — note these; step 3/4 trigger
    ```
    jobs manually instead of waiting for cron, so exact values don't
    matter for this checklist, but confirm they're set to something
    valid (cron expression) or app startup will fail.
    ```

## Amazon session

- [x] Run `make login`. A visible browser opens — complete login (and
  ```
  OTP/CAPTCHA if prompted).
  ```

  - Expected: command exits 0 and `data/browser_state.json` is created/
    updated (check file's modified timestamp).
  - If it fails or exits non-zero: do not proceed — every later step that
    touches Amazon will fail with a CAPTCHA/robot-check screenshot in
    `data/captcha/`.

## Clean starting state (recommended, not required)

- [x] Optional: back up or delete `data/tracker.db` if you want a clean
  ```
  registry for this test pass (`mv data/tracker.db data/tracker.db.bak`).
  Skip this if you intentionally want to test against existing data.
  ```

## Start the app

- [x] Run `make start`.
  - Expected log lines: `SQLite registry initialised at <DB_PATH>`,
    `Web UI available at http://localhost:<WEB_PORT>`,
    `email_digest job registered`, `Scheduler started. Next run: ...`.
- [x] Open `http://localhost:<WEB_PORT>` (or the Docker host address if
  ```
  applicable) in a browser.
  ```

  - Expected: the registration form renders (email, book title, profit %,
    current price fields) — this is `web/templates/register.html`.

Leave `make start` running in its terminal for the rest of this checklist —
steps 3 and 4 will use a **separate** terminal to trigger jobs manually so
you don't have to wait for the cron schedule.
