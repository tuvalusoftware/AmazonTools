# PLAN-001 — C004: Web UI — Registration App

← [plan001.main.md](plan001.main.md)

Delivers the FastAPI web application that lets an author register a book through a browser form. Fields: **email**, **book title**, **profit percentage**, and **current price**. On submit the server resolves the ASIN and inserts the record into the SQLite registry (`data/tracker.db`).

**Depends on:** [plan001.C001_AsinLookup.todo.md](plan001.C001_AsinLookup.todo.md)

---

## Setup

- [x] Create `web/` folder at repo root; add `web/__init__.py` (empty)
- [x] Create `web/templates/` folder
- [x] Confirm `fastapi` and `uvicorn[standard]` are in `requirements.txt`
- [x] Install: `pip install fastapi "uvicorn[standard]"` inside `.venv`

---

## FastAPI app (`web/app.py`)

- [x] Create `web/app.py`
- [x] Instantiate `app = FastAPI(title="Author BSR Tracker")`
- [x] Mount `Jinja2Templates(directory="web/templates")` as `templates`
- [x] `GET /` — renders `register.html` with an empty form context
- [x] `POST /register` — receives form data:
  - `email: str` — validated as a non-empty string containing `@`
  - `title: str` — non-empty
  - `profit_pct: float` — 0–100 range
  - `current_price: float` — > 0
- [x] On validation error re-render `register.html` with `error` context message
- [x] Call `search_asin(title)` (imported from `scripts.lookup_asin`) — wrap in `try/except ValueError`
- [x] On `ValueError` re-render `register.html` with `error="Could not resolve ASIN for that title. Try a more specific title."`
- [x] Call `repo.register_book({"email": email, "title": title, "asin": asin, "profit_pct": profit_pct, "current_price": current_price})`
- [x] On success redirect to `GET /registered?title=<title>`
- [x] `GET /registered` — renders `registered.html` with `title` query param
- [x] `GET /unsubscribe` — accepts query params `email: str` (required) and `asin: str` (optional):
  - If `asin` provided: call `unsubscribe_book(email, asin)`; render `unsubscribe.html` with `mode="book"`, `title` (looked up from registry), `email`
  - If `asin` absent: call `unsubscribe_email(email)`; render `unsubscribe.html` with `mode="all"`, `count` (number deactivated), `email`
  - If neither lookup finds a match, render `unsubscribe.html` with `mode="not_found"`
  - No authentication required — the signed link in the email is the only gate

---

## Registration form (`web/templates/register.html`)

- [x] Create `web/templates/register.html`
- [x] Plain HTML5; include Tailwind CSS via CDN `<script src="https://cdn.tailwindcss.com"></script>`
- [x] Page heading: "Register Your Book"
- [x] Form fields (all required):
  - Email address — `<input type="email" name="email">`
  - Book title — `<input type="text" name="title">`
  - Profit percentage — `<input type="number" name="profit_pct" min="0" max="100" step="0.1">` with label "Profit % per sale"
  - Current price (USD) — `<input type="number" name="current_price" min="0.01" step="0.01">` with label "Current book price ($)"
- [x] Submit button: "Register Book"
- [x] If `error` context is set, show a red alert box above the form
- [x] Responsive layout; centered card on desktop

---

## Confirmation page (`web/templates/registered.html`)

- [x] Create `web/templates/registered.html`
- [x] Show: "✓ {{ title }} has been registered! You will receive daily BSR emails."
- [x] Link back to `GET /` to register another book
- [x] Same Tailwind CDN styling as `register.html`

---

## Unsubscribe page (`web/templates/unsubscribe.html`)

- [x] Create `web/templates/unsubscribe.html`
- [x] Handle three modes via `mode` template variable:
  - `"book"` — show "✓ You have unsubscribed **{{ title }}** from daily tracking. You will no longer receive BSR emails for this book." + link back to `/`
  - `"all"` — show "✓ You have unsubscribed **{{ email }}** from all {{ count }} tracked book(s). No further emails will be sent." + link back to `/`
  - `"not_found"` — show "Nothing to unsubscribe. This link may have already been used or the book was never registered." + link back to `/`
- [x] Same Tailwind CDN styling as `register.html`

---

## Server startup (`main.py`)

- [x] Import `uvicorn` and `web.app.app`
- [x] Start uvicorn in a background thread: `uvicorn.run(app, host="0.0.0.0", port=settings.WEB_PORT)`
- [x] Log `"Web UI available at http://localhost:<WEB_PORT>"` at startup
- [x] Keep existing APScheduler cron jobs running in the main thread

---

## Verification

- [x] Run `python main.py`; open `http://localhost:8080` — confirm registration form renders
- [x] Submit form with a real book title and valid email, profit %, price — confirm redirect to `/registered`
- [x] Query `data/tracker.db` with `sqlite3` CLI — entry has `email`, `title`, `asin`, `profit_pct`, `current_price`, `active=1`
- [x] Submit a second time with the same title — confirm the server handles the duplicate gracefully (show "Already tracked" message or silent success)
- [x] Submit with an unknown title that returns no ASIN — confirm friendly error displayed on form
- [x] Submit with empty fields — confirm HTML5 `required` validation blocks submission before reaching server
- [x] Open `/unsubscribe?email=<email>&asin=<asin>` — confirm `unsubscribe.html` shows `mode="book"` message; row is `active=0` in DB
- [x] Open `/unsubscribe?email=<email>` (no asin) — confirm `mode="all"` message; all rows for that email are `active=0`
- [x] Open `/unsubscribe?email=nobody@test.com` — confirm `mode="not_found"` message, no crash
