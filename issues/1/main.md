# Plan: End-to-end manual test checklist for the Author BSR Tracker

> Issue: TBD — no GitHub remote configured for this repo yet. Once the repo
> is created and pushed, create the GitHub issue and paste its URL here.

## Context

The automated test suite only covers each stage of the pipeline in
isolation, with mocks/seed data replacing the real neighboring stage:

- `tests/test_registry.py`, `tests/test_web_app.py` — unit tests for
  `BookRepo` and the FastAPI routes (`web/app.py`), with `RegisterService.run`
  and `search_asin` mocked out.
- `tests/integration/test_lookup_asin_integration.py` — live ASIN
  resolution only.
- `tests/integration/test_scrape_bsr_integration.py` — live BSR/price
  scrape for a fixed list of known ASINs (`_scrape_bsr`), never wired to the
  registry or the web form.
- `tests/integration/test_email_digest_integration.py` — renders and
  optionally sends the digest from hand-seeded snapshot data, not from a
  book that was actually registered and scraped.
- `tests/test_pdf_service.py` — PDF generation with fully mocked data.

**Registration flow (as of Issue 2)** is now async: `POST /register` returns
`pending.html` in < 1 s; ASIN lookup + DB write + confirmation email run in a
background thread via `RegisterService` (`web/register_service.py`). Three
email outcomes:

- **Found** → insert into `tracked_books` → "registration confirmed" email.
- **Not found** → no DB write → "could not find book" email.
- **Duplicate** → no insert → "already tracking" email.

No test — automated or manual — walks the real user journey with a person
watching each screen: open the browser → fill the registration form → see the
pending page → wait for the confirmation email → wait for/trigger a scrape →
check the SQLite data is right → trigger the digest job → open the received
email → open the PDF attachment → click unsubscribe → confirm the book stops
appearing.

**Scope decision**:

1. This issue is a **manual test checklist**, not automated test code. The
   deliverable is `issues/1/*.md` documents a human follows step-by-step,
   ticking boxes and recording actual vs. expected results.
2. It runs against the app started locally with `make start` (jobs
   triggered on demand via `make run-job`, which interactively prompts for
   scrape / digest / both) — real Amazon session, real SQLite file at
   `data/tracker.db`, real Gmail SMTP. No test doubles.
3. Out of scope: writing/extending `pytest` integration tests — those
   already exist per-stage (see Context above) and are a separate,
   automation-focused effort if wanted later.
4. Out of scope: Docker-based execution (`docker compose up`) — this
   checklist assumes a local `make start` run. A Docker variant can reuse
   the same steps later if needed.
5. Out of scope: creating the GitHub repo/issue for this. The user handles
   that separately; this plan only covers the local checklist docs.

## Checklist kỹ thuật

- [ ] [1. Preconditions & environment setup](./01-preconditions.md)
- [ ] [2. Register a book through the Web UI](./02-register-flow.md)
- [ ] [3. BSR/price scrape run — verify data lands in SQLite](./03-scrape-flow.md)
- [ ] [4. Email digest run — verify email + PDF attachment](./04-digest-and-pdf.md)
- [ ] [5. Unsubscribe flow + negative/edge cases](./05-unsubscribe-and-edge-cases.md)

## Việc liên quan cần cân nhắc nhưng để ngoài phạm vi

- Automated `pytest` e2e coverage chaining all stages together — a natural
  follow-up once this manual checklist has been run once and is known to
  pass, but a separate effort (different skillset: writing test code vs.
  running the app).
- Docker-level manual test (`docker compose up` + hit the container over
  HTTP) — same steps could apply but env/volume setup differs enough to
  warrant its own pass later.
- Load/concurrency testing, real browser automation of our own UI
  (Selenium/Playwright driving `web/app.py`'s pages) — not needed for a
  manual checklist.

## Test thủ công (checklist tổng — chi tiết từng bước ở các file con)

- [ ] Preconditions verified (session, `.env`, server running) — see
      [01-preconditions.md](./01-preconditions.md)
- [ ] Registration through the browser shows the pending page immediately
      and confirmation email arrives within ~1 minute; book persists to SQLite —
      see [02-register-flow.md](./02-register-flow.md)
- [ ] A scrape run produces a BSR/price snapshot for the registered book —
      see [03-scrape-flow.md](./03-scrape-flow.md)
- [ ] A digest run sends an email with correct rank/price and a valid PDF
      attachment — see [04-digest-and-pdf.md](./04-digest-and-pdf.md)
- [ ] Unsubscribe links work and edge cases (bad title, duplicate
      registration, no active books) behave as expected — see
      [05-unsubscribe-and-edge-cases.md](./05-unsubscribe-and-edge-cases.md)

## Verification

- No automated command to run — this issue's "verification" is the tester
  filling in actual-result columns/checkboxes in the sub-docs and reporting
  any mismatch as a bug (with screenshot/log excerpt) rather than a CI
  status.
