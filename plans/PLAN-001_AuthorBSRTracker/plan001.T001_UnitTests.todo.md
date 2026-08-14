# PLAN-001 — T001: Unit Tests

← [plan001.main.md](plan001.main.md)

Plans all unit tests for the Author BSR Tracker feature set. Tests live under `tests/` at the repo root and use `pytest` + `pytest-asyncio`. All external I/O (SQLite, SMTP, Playwright, Amazon HTTP) is mocked or uses an in-memory SQLite database.

**Depends on:** all implementation chapters (C001 – C006A must be done before tests can be written)

---

## Setup

- [x] Create `tests/` folder at repo root; add `tests/__init__.py` (empty)
- [x] Add `pytest`, `pytest-asyncio`, `httpx` (for FastAPI test client) to `requirements.txt`
- [x] Add `conftest.py` under `tests/` — shared fixtures:
  - `tmp_db(tmp_path)` — creates a fresh in-memory (or `tmp_path`) SQLite DB, calls `BookRepo(db_path).init_db()`, yields a `BookRepo` instance; tears down after test
  - `sample_book()` — returns a canonical `dict` with `email`, `title`, `asin`, `profit_pct`, `current_price` for reuse across tests
  - `sample_snapshots(asin, n=5)` — returns `n` `BestSellerRank` dataclass instances with staggered `scraped_at` timestamps for a given ASIN
- [x] Confirm all tests can be run with `pytest tests/` from repo root

---

## `tests/test_registry.py` — `BookRepo` (C001, C002)

### Schema initialisation

- [x] `test_init_db_creates_tables` — call `BookRepo(tmp_db).init_db()`; assert `tracked_books` and `bsr_snapshots` tables exist via `sqlite_master` query
- [x] `test_init_db_idempotent` — call `init_db()` twice on the same path; assert no exception raised

### `register_book`

- [x] `test_register_book_returns_true_on_insert` — register new book; assert returns `True`; assert row exists with `active=1`
- [x] `test_register_book_returns_false_on_active_duplicate` — register same ASIN twice; assert second call returns `False`
- [x] `test_register_book_reactivates_inactive` — register, unsubscribe (set `active=0`), register again; assert returns `True` and row is `active=1`

### `unsubscribe_book`

- [x] `test_unsubscribe_book_returns_true` — register then unsubscribe; assert returns `True`; row `active=0`
- [x] `test_unsubscribe_book_returns_false_when_not_found` — unsubscribe an ASIN that was never registered; assert returns `False`
- [x] `test_unsubscribe_book_only_affects_matching_row` — register two ASINs for same email; unsubscribe one; assert only that row is `active=0`

### `unsubscribe_email`

- [x] `test_unsubscribe_email_returns_count` — register 3 books for same email; call `unsubscribe_email`; assert returns `3`
- [x] `test_unsubscribe_email_returns_zero_when_none_active` — register and unsubscribe all; call again; assert returns `0`

### `load_active_books`

- [x] `test_load_active_books_excludes_inactive` — register 2 books; unsubscribe 1; assert `load_active_books()` returns only the active one
- [x] `test_load_active_books_empty_db` — fresh DB; assert returns `[]`
- [x] `test_load_active_books_returns_plain_dicts` — assert each element is a `dict` (not `sqlite3.Row`)

### `save_bsr_snapshots`

- [x] `test_save_bsr_snapshots_returns_count` — pass 3 `BestSellerRank` objects; assert return value is `3`
- [x] `test_save_bsr_snapshots_inserts_all_rows` — insert 3 rows; query `bsr_snapshots`; assert 3 rows present
- [x] `test_save_bsr_snapshots_persists_price` — include `price=14.99` on a `BestSellerRank`; assert `bsr_snapshots.price` equals `14.99`

### `load_latest_snapshot`

- [x] `test_load_latest_snapshot_returns_most_recent` — insert 2 snapshots at different timestamps; assert returned `scraped_at` is the later one
- [x] `test_load_latest_snapshot_returns_none_when_empty` — fresh DB; assert returns `None`

---

## `tests/test_snapshot_repo.py` — `SnapshotRepo` (C006A)

- [x] `test_load_daily_snapshots_returns_empty_for_no_data` — fresh DB; assert returns `[]`
- [x] `test_load_daily_snapshots_aggregates_by_date` — insert 2 rows same date, different ranks; assert one `DailySnapshotRow` per date
- [x] `test_load_daily_snapshots_uses_best_rank_per_day` — same date rows with ranks `50` and `200`; assert `rank == 50`
- [x] `test_load_daily_snapshots_uses_highest_price_per_day` — same date rows with prices `9.99` and `14.99`; assert `price == 14.99`
- [x] `test_load_daily_snapshots_sorted_oldest_first` — three dates inserted out of order; assert result is ascending by date
- [x] `test_load_daily_snapshots_days_window` — insert 10 days of rows; call with `days=5`; assert only 5 `DailySnapshotRow`s returned
- [x] `test_load_daily_snapshots_days_zero_returns_all` — call with `days=0`; assert all rows returned

---

## `tests/test_lookup_asin.py` — `search_asin` (C001)

- [x] `test_search_asin_returns_title_and_asin` — mock `fetch_page_html` to return HTML with a `div[data-asin="0735211299"]`; call `search_asin("Atomic Habits")`; assert returns `("Atomic Habits", "0735211299")`
- [x] `test_search_asin_uses_first_candidate` — mock HTML with multiple `[data-asin]` elements; assert returned ASIN is from the first element
- [x] `test_search_asin_raises_value_error_when_no_asin` — mock `fetch_page_html` to return HTML with no `[data-asin]` attributes; assert `ValueError` raised
- [x] `test_search_asin_ignores_empty_data_asin` — mock HTML where first result has `data-asin=""`; assert falls through to next non-empty candidate

---

## `tests/test_scrape_bsr.py` — `jobs/scrape_bsr.py` (C002, C004A)

- [x] `test_run_skips_when_no_active_books` — mock `load_active_books` returns `[]`; call `run()`; assert `save_bsr_snapshots` is not called; assert WARNING log contains `"No active ASINs"`
- [x] `test_run_queries_active_books_from_registry` — mock `load_active_books` returns one book; mock `_scrape_bsr`; assert `_scrape_bsr` called with correct ASIN
- [x] `test_bestsellerrank_price_field_defaults_to_zero` — construct `BestSellerRank(asin="X", rank=1, category="cat", scraped_at="now")`; assert `price == 0.0`
- [x] `test_price_scraped_from_first_selector` — mock page HTML containing `<span class="a-offscreen">$14.99</span>`; assert returned `BestSellerRank.price == 14.99`
- [x] `test_price_falls_back_through_selectors` — mock HTML with only `span#kindle-price` containing `$9.99`; assert `price == 9.99`
- [x] `test_price_defaults_to_zero_when_no_selector_matches` — mock HTML with no price selectors; assert `price == 0.0`, no exception

---

## `tests/test_email_digest.py` — `jobs/email_digest.py` (C003, C006)

### `build_digest_html`

- [x] `test_build_digest_html_renders_book_title` — mock `BookRepo` with one active book; assert rendered HTML contains the book title
- [x] `test_build_digest_html_includes_rank_formatted` — mock `load_latest_snapshot` returning `{rank: 1523}`; assert HTML contains `#1,523`
- [x] `test_build_digest_html_includes_unsubscribe_book_url` — assert HTML contains link with `email=` and `asin=` query params
- [x] `test_build_digest_html_includes_unsubscribe_all_url` — assert HTML contains link with only `email=` query param (no `asin`)
- [x] `test_build_digest_html_shows_no_rank_when_none` — mock `load_latest_snapshot` returning `None`; assert HTML contains `"No rank data yet"` text
- [x] `test_build_digest_html_computes_estimated_daily_profit` — book with `current_price=20.0`, `profit_pct=0.70`; snapshot rank produces non-zero units; assert `estimated_daily_profit > 0` in rendered HTML
- [x] `test_build_digest_html_reads_price_from_snapshot` — mock snapshot with `price=14.99` and `tracked_books.current_price=0.0`; assert rendered price is `$14.99`

### `send_email`

- [x] `test_send_email_html_only_uses_alternative_mime` — mock `smtplib.SMTP`; call `send_email(to, subject, html)`; assert `MIMEMultipart("alternative")` used, no `"mixed"` envelope
- [x] `test_send_email_with_attachment_uses_mixed_mime` — call `send_email(to, subject, html, attachment=Path("report.pdf"))`; assert outer MIME type is `"mixed"`
- [x] `test_send_email_with_attachment_includes_pdf_part` — mock `Path.read_bytes`; assert `MIMEApplication` part present with correct `filename`
- [x] `test_send_email_logs_smtp_error_without_raising` — mock `SMTP.login` to raise `smtplib.SMTPAuthenticationError`; call `send_email`; assert no exception propagates; assert ERROR log emitted

### `run` (digest job)

- [x] `test_run_skips_when_no_active_books` — mock `load_active_books` returns `[]`; assert `send_email` not called; assert WARNING logged
- [x] `test_run_groups_books_by_email` — mock two books for the same email + one for a different email; assert `send_email` called exactly twice
- [x] `test_run_deletes_temp_pdf_after_send` — mock `Service_Pdf_GenFromAsin.run` to produce a real temp file; assert file is deleted after `run()` completes
- [x] `test_run_subject_contains_today_date` — call `run()`; capture `send_email` arguments; assert subject contains today's ISO date

---

## `tests/test_web_app.py` — `web/app.py` (C004, C004A)

Use `httpx.AsyncClient` with `app` from `web.app`.

### `POST /register`

- [x] `test_post_register_redirects_on_success` — mock `search_asin` returning a valid ASIN; mock `BookRepo.register_book` returning `True`; assert redirect to `/registered`
- [x] `test_post_register_rerenders_on_asin_not_found` — mock `search_asin` raising `ValueError`; assert 200 response contains error message `"Could not resolve ASIN"`
- [x] `test_post_register_rerenders_on_validation_error` — post with `profit_pct=-1`; assert 200 response contains an error message
- [x] `test_post_register_passes_price_zero_to_repo` — mock `search_asin`; capture `register_book` call args; assert `current_price=0.0` (C004A — no user price field)

### `GET /registered`

- [x] `test_get_registered_shows_title` — call `GET /registered?title=Atomic+Habits`; assert `"Atomic Habits"` in response body

### `GET /unsubscribe`

- [x] `test_unsubscribe_book_mode` — mock `BookRepo.unsubscribe_book` returning `True`; assert response contains `"mode=book"` content
- [x] `test_unsubscribe_all_mode` — call without `asin` param; mock `unsubscribe_email` returning `2`; assert response contains `"mode=all"` content
- [x] `test_unsubscribe_not_found_mode` — mock `unsubscribe_book` returning `False` and `unsubscribe_email` returning `0`; assert response contains `"not_found"` content

---

## `tests/test_pdf_loader.py` — `Helper_Pdf_Loader` (C006)

- [x] `test_load_returns_none_when_fewer_than_two_snapshots` — mock `SnapshotRepo.load_daily_snapshots` returning `[one_row]`; assert `load()` returns `None`
- [x] `test_load_returns_book_raw_data_with_correct_keys` — mock 3 snapshot rows; assert return value has keys `asin`, `title`, `profit_pct`, `snapshot_rows`
- [x] `test_load_uses_profit_pct_from_tracked_books` — book row has `profit_pct=0.60`; assert `BookRawData["profit_pct"] == 0.60`
- [x] `test_load_falls_back_to_default_profit_pct` — `tracked_books` has `profit_pct=0`; assert fallback `profit_pct == 0.70`
- [x] `test_load_snapshot_rows_are_oldest_first` — mock rows with dates `["2026-08-03", "2026-08-01", "2026-08-02"]`; assert `snapshot_rows[0]["date"] == "2026-08-01"`

---

## `tests/test_pdf_metrics.py` — `Helper_Pdf_Metrics` (C006)

- [x] `test_compute_returns_book_metrics_data` — pass minimal `BookRawData` with 5 rows; assert all expected keys present in result
- [x] `test_compute_units_per_day_uses_power_law` — row with `rank=10000`; assert `units_per_day[i] == max(1, round(10000 / 10000 ** 0.70))`
- [x] `test_compute_daily_profit_uses_snapshot_price` — row with `rank=1000`, `price=10.0`; book `profit_pct=0.70`; assert `profit_per_day[i] == estimated_units * 10.0 * 0.70`
- [x] `test_compute_cumulative_units_is_running_total` — two rows with `units_per_day=[3, 5]`; assert `cumulative_units == [3, 8]`
- [x] `test_compute_monthly_rows_excludes_current_month` — rows spanning current (partial) month only; assert `monthly_rows == []`
- [x] `test_compute_monthly_rows_includes_all_complete_months` — rows spanning 3 complete months; assert `len(monthly_rows) == 3`
- [x] `test_compute_monthly_row_label_format` — complete month of Jul 2026; assert `MonthlyRow.label == "Jul 2026"`
- [x] `test_compute_series_lengths_match_snapshot_rows` — 7 snapshot rows; assert `dates`, `units_per_day`, `profit_per_day`, `cumulative_units`, `cumulative_profit` all have length 7

---

## `tests/test_pdf_service.py` — `Service_Pdf_GenFromAsin` (C006)

- [x] `test_run_returns_output_path` — mock `Helper_Pdf_Loader.load`, `Helper_Pdf_Metrics.compute`, `Helper_Pdf_Renderer.render_book`, `PdfPages`; assert `run()` returns a `Path`
- [x] `test_run_skips_asin_with_no_data` — mock `loader.load` returning `None`; assert `render_book` not called; assert WARNING logged
- [x] `test_run_filters_to_single_asin` — construct with `asin_filter="B0001"`; mock `load_active_books` returning two books; assert `loader.load` called only once with `"B0001"`
- [x] `test_run_all_active_books_when_no_filter` — `asin_filter=None`; mock `load_active_books` returning two books; assert `loader.load` called twice
- [x] `test_run_uses_custom_output_path` — pass `output_path=Path("/tmp/custom.pdf")`; assert returned path equals `/tmp/custom.pdf`

---

## `tests/test_config.py` — `config.py` (C002)

- [x] `test_smtp_settings_defaults` — import `settings`; assert `settings.smtp.host == "smtp.gmail.com"` and `settings.smtp.port == 587`
- [x] `test_db_path_default` — assert `settings.DB_PATH` contains `"tracker.db"`

---

## Verification

- [ ] `pip install pytest pytest-asyncio httpx` in `.venv`
- [ ] `pytest tests/ -v` — all tests pass (no live network or SMTP calls)
- [ ] `pytest tests/ --tb=short` — zero failures, zero errors
- [ ] Confirm no `data/` files or temp PDFs are left behind after test suite completes
