# PLAN-001 — C004: Web UI — Registration App

← [plan001.main.md](plan001.main.md)

Delivers the FastAPI web application that lets an author register a book through a browser form. Fields: **email**, **book title**, **profit percentage**, and **current price**. On submit the server resolves the ASIN and inserts the record into the SQLite registry (`data/tracker.db`).

**Depends on:** [plan001.C001_AsinLookup.todo.md](plan001.C001_AsinLookup.todo.md)

---

## Setup

- [ ] Create `web/` folder at repo root; add `web/__init__.py` (empty)
- [ ] Create `web/templates/` folder
- [ ] Confirm `fastapi` and `uvicorn[standard]` are in `requirements.txt`
- [ ] Install: `pip install fastapi "uvicorn[standard]"` inside `.venv`

---

## FastAPI app (`web/app.py`)

- [ ] Create `web/app.py`
- [ ] Instantiate `app = FastAPI(title="Author BSR Tracker")`
- [ ] Mount `Jinja2Templates(directory="web/templates")` as `templates`
- [ ] `GET /` — renders `register.html` with an empty form context
- [ ] `POST /register` — receives form data:
  - `email: str` — validated as a non-empty string containing `@`
  - `title: str` — non-empty
  - `profit_pct: float` — 0–100 range
  - `current_price: float` — > 0
- [ ] On validation error re-render `register.html` with `error` context message
- [ ] Call `search_asin(title)` (imported from `scripts.lookup_asin`) — wrap in `try/except ValueError`
- [ ] On `ValueError` re-render `register.html` with `error="Could not resolve ASIN for that title. Try a more specific title."`
- [ ] Call `register_book(email, title, asin, profit_pct, current_price)`
- [ ] On success redirect to `GET /registered?title=<title>`
- [ ] `GET /registered` — renders `registered.html` with `title` query param
- [ ] `GET /unsubscribe` — accepts query params `email: str` (required) and `asin: str` (optional):
  - If `asin` provided: call `unsubscribe_book(email, asin)`; render `unsubscribe.html` with `mode="book"`, `title` (looked up from registry), `email`
  - If `asin` absent: call `unsubscribe_email(email)`; render `unsubscribe.html` with `mode="all"`, `count` (number deactivated), `email`
  - If neither lookup finds a match, render `unsubscribe.html` with `mode="not_found"`
  - No authentication required — the signed link in the email is the only gate

---

## Registration form (`web/templates/register.html`)

- [ ] Create `web/templates/register.html`
- [ ] Plain HTML5; include Tailwind CSS via CDN `<script src="https://cdn.tailwindcss.com"></script>`
- [ ] Page heading: "Register Your Book"
- [ ] Form fields (all required):
  - Email address — `<input type="email" name="email">`
  - Book title — `<input type="text" name="title">`
  - Profit percentage — `<input type="number" name="profit_pct" min="0" max="100" step="0.1">` with label "Profit % per sale"
  - Current price (USD) — `<input type="number" name="current_price" min="0.01" step="0.01">` with label "Current book price ($)"
- [ ] Submit button: "Register Book"
- [ ] If `error` context is set, show a red alert box above the form
- [ ] Responsive layout; centered card on desktop

---

## Confirmation page (`web/templates/registered.html`)

- [ ] Create `web/templates/registered.html`
- [ ] Show: "✓ {{ title }} has been registered! You will receive daily BSR emails."
- [ ] Link back to `GET /` to register another book
- [ ] Same Tailwind CDN styling as `register.html`

---

## Unsubscribe page (`web/templates/unsubscribe.html`)

- [ ] Create `web/templates/unsubscribe.html`
- [ ] Handle three modes via `mode` template variable:
  - `"book"` — show "✓ You have unsubscribed **{{ title }}** from daily tracking. You will no longer receive BSR emails for this book." + link back to `/`
  - `"all"` — show "✓ You have unsubscribed **{{ email }}** from all {{ count }} tracked book(s). No further emails will be sent." + link back to `/`
  - `"not_found"` — show "Nothing to unsubscribe. This link may have already been used or the book was never registered." + link back to `/`
- [ ] Same Tailwind CDN styling as `register.html`

---

## Server startup (`main.py`)

- [ ] Import `uvicorn` and `web.app.app`
- [ ] Start uvicorn in a background thread: `uvicorn.run(app, host="0.0.0.0", port=settings.WEB_PORT)`
- [ ] Log `"Web UI available at http://localhost:<WEB_PORT>"` at startup
- [ ] Keep existing APScheduler cron jobs running in the main thread

---

## Verification

- [ ] Run `python main.py`; open `http://localhost:8080` — confirm registration form renders
- [ ] Submit form with a real book title and valid email, profit %, price — confirm redirect to `/registered`
- [ ] Query `data/tracker.db` with `sqlite3` CLI — entry has `email`, `title`, `asin`, `profit_pct`, `current_price`, `active=1`
- [ ] Submit a second time with the same title — confirm the server handles the duplicate gracefully (show "Already tracked" message or silent success)
- [ ] Submit with an unknown title that returns no ASIN — confirm friendly error displayed on form
- [ ] Submit with empty fields — confirm HTML5 `required` validation blocks submission before reaching server
- [ ] Open `/unsubscribe?email=<email>&asin=<asin>` — confirm `unsubscribe.html` shows `mode="book"` message; row is `active=0` in DB
- [ ] Open `/unsubscribe?email=<email>` (no asin) — confirm `mode="all"` message; all rows for that email are `active=0`
- [ ] Open `/unsubscribe?email=nobody@test.com` — confirm `mode="not_found"` message, no crash
