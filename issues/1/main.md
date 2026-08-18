# Plan: End-to-end test for the Author BSR Tracker

> Issue: TBD — no GitHub remote configured for this repo yet. Once the repo is
> created and pushed, create the GitHub issue and paste its URL here.

## Context

The test suite already covers each piece of the pipeline in isolation:

- `tests/test_registry.py`, `tests/test_web_app.py` — unit tests for `BookRepo`
  and the FastAPI routes (`web/app.py`), using an in-memory/temp SQLite DB and
  mocked `search_asin`.
- `tests/integration/test_lookup_asin_integration.py` — live ASIN resolution
  against real Amazon search.
- `tests/integration/test_scrape_bsr_integration.py` — live BSR/price scrape
  for a fixed list of known ASINs (`_scrape_bsr`), not wired to the registry.
- `tests/integration/test_email_digest_integration.py` — renders
  `_build_digest_html` from seeded snapshot data and optionally sends it via
  real Gmail SMTP (`test_send_digest_email_real`), but the seed data is
  hand-written, not produced by an actual scrape.
- `tests/test_pdf_service.py` — unit-level PDF generation from seeded data.

None of these chain together. There is no test that drives the real user
journey: register a book through the Web UI → resolve its ASIN for real →
scrape its live BSR/price → persist it → generate a PDF report from that data
→ send the email digest — and checks that each stage's output is exactly what
the next stage consumes.

**Scope decision**:

1. This issue adds ONE new end-to-end integration test module,
   `tests/integration/test_e2e_flow.py`, that chains the real components
   together against live Amazon + live Gmail SMTP. It reuses the existing
   pieces (`web.app`, `scripts.lookup_asin`, `jobs.scrape_bsr`,
   `jobs.email_digest`, PDF report generation, `utils.registry.BookRepo`) —
   it does not rewrite them.
2. It runs under the existing `integration` pytest marker
   (`make test-integration`) — same session/SMTP prerequisites as today. It is
   explicitly NOT a new test tier or CI-only suite.
3. Out of scope: Docker/container-level e2e (hitting the app through
   `docker compose up`), load/concurrency testing, and browser-driven UI
   clicking (Selenium/Playwright against the rendered HTML pages) — the Web UI
   layer is exercised via FastAPI's `TestClient`, not a real browser.
4. Out of scope: creating the GitHub repo/issue for this. The user will handle
   that separately; this plan only covers the local docs + the test code.

## Checklist kỹ thuật

- [ ] [1. E2E fixture: isolated DB + app wiring](./01-fixture-and-app-wiring.md)
- [ ] [2. Register flow (Web UI → ASIN resolve → persist)](./02-register-flow.md)
- [ ] [3. Scrape flow (live BSR/price → snapshot persisted)](./03-scrape-flow.md)
- [ ] [4. Report flow (PDF generation → email digest send)](./04-report-and-email-flow.md)
- [ ] [5. Cleanup, skip conditions, and Makefile wiring](./05-cleanup-and-runner.md)

## Việc liên quan cần cân nhắc nhưng để ngoài phạm vi

- Docker-level e2e (`docker compose up` + hit the container over HTTP) — would
  need its own harness; tracked separately if wanted later.
- Real browser UI automation (Playwright against the rendered pages) — the
  existing scraping already uses Playwright for Amazon; adding it for our own
  UI too is a separate, heavier investment.
- CI wiring for this test (it needs a live Amazon session + Gmail App
  Password secrets) — left as a manual `make test-integration` run for now.

## Test thủ công

- [ ] Run `make login` to refresh the Amazon session, then
      `make test-integration tests/integration/test_e2e_flow.py` — the test
      registers a real book title (e.g. "Atomic Habits"), resolves its ASIN,
      scrapes its live BSR, confirms a `bsr_snapshots` row was written, builds
      a PDF report, builds the digest HTML, and (if `SMTP__PASSWORD` and
      `SMTP__FROM_ADDR` are set) sends the digest to `SMTP__FROM_ADDR` for
      manual inbox inspection.
- [ ] Without SMTP credentials set, the same command still runs the
      register → scrape → persist → PDF/HTML-build assertions and only skips
      the actual send step.

## Verification

- `make test` — unit suite must stay green (no regressions from any shared
  fixture changes in `tests/conftest.py`).
- `make test-integration tests/integration/test_e2e_flow.py -v -s` — the new
  e2e test itself, run after `make login`.
