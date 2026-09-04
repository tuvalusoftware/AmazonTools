# Issue 2 — Async register flow with email confirmation

> GitHub issue: TBD (no remote configured yet).

## Target

- `POST /register` returns a "request received" page in **< 1 s** — no blocking wait.
- ASIN lookup + DB write + confirmation email all run in a background thread.
- Three email outcomes:
  - **Found** → insert into `tracked_books` → send "registration confirmed" email.
  - **Not found** → no DB write → send "could not find book" email echoing the input.
  - **Duplicate** (email + ASIN already active) → no insert → send "already tracking" email.

## What already have

- `web/app.py` — `POST /register` now returns `pending.html` immediately; enqueues `RegisterService(...).run` via `BackgroundTasks`.
- `web/register_service.py` — `RegisterService` class: `run()` owns ASIN lookup → DB write → email dispatch; three private `_email_*` builder methods.
- `web/templates/pending.html` — amber/spinner "request received" page.
- `scripts/lookup_asin.py` — `search_asin(title)` uses Playwright; worst-case ~96 s.
- `jobs/email_digest.py` — `send_email(to, subject, html_body, attachment)`; thread-safe.
- `config.settings.smtp` — SMTP credentials wired via pydantic-settings.
- `tests/test_web_app.py` — route tests updated; `RegisterService.run` tests pending (step 4).

## What should do in next step

Checklist (each item links to its detail doc):

- [x] [1. Background task — `RegisterService` in `web/register_service.py`](./01-background-task-infra.md)
- [x] [2. Email templates for registration outcomes](./02-email-templates.md)
- [x] [3. Route changes — `/register` and `/pending`](./03-web-route-changes.md)
- [x] [4. Unit tests — `RegisterService.run` scenarios](./04-unit-tests.md)

**Manual smoke test** (after step 4):

| Step | Action | Expected |
|------|--------|----------|
| 1 | Submit valid title + real inbox | `/pending` page in < 1 s; confirmation email arrives within ~20 s; ASIN row in DB. |
| 2 | Submit same email + title again | `/pending` immediately; "already tracking" email; no duplicate DB row. |
| 3 | Submit unresolvable title | `/pending` immediately; "could not find book" email. |
| 4 | `GET /registered` directly | Renders without error (kept for backward compatibility). |

**Sample form data** (used for manual testing):

| Field | Value |
|-------|-------|
| Email | `leanhkhoi2611@gmail.com` |
| Book title | `Theo of Golden: A Novel` |
| Profit % | `70` |
| Book price (USD) | `0` |

```
make test    # must stay green (unit + no-integration)
```

## What consider later

- `/status` polling endpoint — if lookup latency grows (e.g. Playwright replaced by slower fallback).
- Persist a "pending" row for admin visibility — only worthwhile with an admin dashboard.
- Rate-limit / deduplicate concurrent identical form submissions — relevant when app goes public.
- Replace Playwright in `search_asin` with `httpx` — could cut lookup from ~10 s to ~2 s; independent of this change.
