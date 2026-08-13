# PLAN-001 — C003: Email Digest Job

← [plan001.main.md](plan001.main.md)

Delivers `jobs/email_digest.py` and `templates/digest.html` — queries all active tracked books from SQLite, builds an HTML email per registered author, and sends it via SMTP. Each email includes the author's book economics (profit % and current price) plus one-click unsubscribe links.

**Depends on:** [plan001.C002_BsrJobExtension.todo.md](plan001.C002_BsrJobExtension.todo.md)

---

## Jinja2 template (`templates/digest.html`)

- [x] Create `templates/` folder at repo root
- [x] Create `templates/digest.html` — minimal HTML email layout
- [x] Template variables:
  - `email: str` — recipient email address (used in footer unsubscribe link)
  - `books: list` — each item: `{title, asin, current_rank, category, trend, profit_pct, current_price, estimated_daily_profit, unsubscribe_book_url}`
  - `unsubscribe_all_url: str` — footer-level unsubscribe for the whole address
- [x] `current_rank` — most recent rank integer; display as `#1,523`
- [x] `category` — full category path string
- [x] `trend` — list of `{date, rank}` for up to 7 prior days; render as a simple table row (not a chart)
- [x] `profit_pct` — display as `70%`
- [x] `current_price` — display as `$14.99`
- [x] `estimated_daily_profit` — optional computed field (see email builder notes)
- [x] Each book row includes a small "Unsubscribe this book" link pointing to `unsubscribe_book_url`
- [x] Email footer includes an "Unsubscribe all emails for {{ email }}" link pointing to `unsubscribe_all_url`
- [x] Use inline CSS only — no external stylesheets (email clients strip `<head>` styles)
- [x] Show a friendly "No rank data yet" row when `current_rank` is `None`

---

## Snapshot reader helper

- [x] In `utils/registry.py` add `load_latest_snapshot(self, asin: str) -> dict | None` to `BookRepo`:
  - Query: `SELECT rank, category, scraped_at FROM bsr_snapshots WHERE asin=? ORDER BY scraped_at DESC LIMIT 1`
  - Return a plain dict `{rank, category, scraped_at}` or `None` if no rows exist
- [x] Add `load_rank_history(self, asin: str, days: int = 7) -> list[dict]` to `BookRepo`:
  - Query: `SELECT DATE(scraped_at) as date, rank FROM bsr_snapshots WHERE asin=? ORDER BY scraped_at DESC LIMIT ?` with `days` as limit
  - Deduplicate by date (keep lowest rank per day)
  - Return list of `{date: str, rank: int}` sorted oldest-first

---

## Email builder

- [x] Import `jinja2.Environment, FileSystemLoader` — load template from `templates/`
- [x] Import `urllib.parse.quote` for building unsubscribe URLs
- [x] Write `build_digest_html(email: str, books: list[dict]) -> str`
  - Instantiate `BookRepo()`; for each tracked book call `repo.load_latest_snapshot(asin)` + `repo.load_rank_history(asin)`
  - Pass `profit_pct` and `current_price` from registry record into template context
  - Optionally compute `estimated_daily_profit = current_price * (profit_pct / 100)` and include it
  - Build per-book `unsubscribe_book_url = f"{settings.WEB_BASE_URL}/unsubscribe?email={quote(email)}&asin={asin}"`
  - Build `unsubscribe_all_url = f"{settings.WEB_BASE_URL}/unsubscribe?email={quote(email)}"`
  - Assemble the template context; render and return HTML string
- [x] Write `send_email(to: str, subject: str, html_body: str) -> None`
  - Use `smtplib.SMTP` with STARTTLS (`settings.SMTP_PORT == 587`) or `SMTP_SSL` (`465`)
  - Login with `settings.SMTP_USER` / `settings.SMTP_PASSWORD`
  - Build `email.mime.multipart.MIMEMultipart("alternative")` + `MIMEText(html_body, "html")`
  - Send to the provided `to` address (per-book email from registry)
  - Log success and recipient at INFO; log SMTP errors at ERROR (do not raise)

---

## Digest job entry point

- [x] Write `run() -> None` in `jobs/email_digest.py`
  - Call `load_active_books()` from `utils.registry` — returns only `active=1` rows
  - Skip and log a warning when no active books are tracked
  - Group books by `email` — one digest email per unique author email address
  - For each unique email call `build_digest_html(email, books_for_author)` then `send_email(email, subject, html)`
  - Subject: `"📚 Daily BSR Digest — <date>"`
  - Log total authors emailed

---

## Scheduler registration (`main.py`)

- [x] Import `run as email_digest_run` from `jobs.email_digest`
- [x] Add job with `CronTrigger.from_crontab(settings.EMAIL_DIGEST_CRON)`, id `"email_digest"`
- [x] Log `"email_digest job registered"` at startup

---

## Verification

- [ ] Set real `SMTP_*` values and at least one active row in `data/tracker.db` with BSR data in `bsr_snapshots`
- [ ] Run `python -c "from jobs.email_digest import run; run()"` — confirm email received
- [ ] Verify subject line contains today's date
- [ ] Verify each tracked book appears with its current rank, profit %, and price
- [ ] Verify each book row contains a "Unsubscribe this book" link with correct `email` and `asin` query params
- [ ] Verify the email footer contains an "Unsubscribe all" link with correct `email` query param
- [ ] Test with empty `tracked_books` table — confirm warning logged, no email sent, no crash
- [ ] Test with all records `active=0` — confirm warning logged (load_active_books returns []), no email sent
- [ ] Test with a missing `SMTP_PASSWORD` — confirm error logged, no unhandled exception
