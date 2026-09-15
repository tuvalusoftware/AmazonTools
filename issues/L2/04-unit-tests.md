# 4. Unit tests

> Parent overview: [Issue 2 — Async register flow](./main.md)

## What was done

`tests/test_web_app.py` was rewritten to match the new async architecture.
All tests pass with `make test`.

## Key patch paths

Because the pipeline logic now lives in `web/register_service.py`, mocks
target that module:

| Symbol | Patch target |
|--------|-------------|
| `search_asin` | `web.register_service.search_asin` |
| `BookRepo` | `web.register_service.BookRepo` |
| `send_email` | `web.register_service.send_email` |
| `RegisterService.run` | `web.register_service.RegisterService.run` |

> Note: `TestClient` runs `BackgroundTasks` **synchronously**, so the
> background function executes during the test call and mocks are active.

## Test inventory

### `POST /register` route tests

| Test | What it checks |
|------|---------------|
| `test_post_register_returns_pending_on_valid_form` | Valid form → 200, pending page, `RegisterService.run` called once |
| `test_post_register_rerenders_on_validation_error` | `profit_pct=-1` → 200 with error message |
| `test_post_register_rerenders_on_missing_current_price` | Missing field → 422 from FastAPI |

### `RegisterService.run` tests (patch via `web.register_service.*`)

| Test | Scenario |
|------|---------|
| T1 — success | ASIN found, new insert → `_email_confirmed` sent |
| T2 — not found | `search_asin` raises `ValueError` → `_email_not_found` sent, no DB write |
| T3 — duplicate | `register_book` returns `False` → `_email_duplicate` sent |
| T4 — unexpected error | `search_asin` raises `RuntimeError` → `_email_not_found` sent, no crash |

### Unchanged tests

- `test_get_registered_shows_title` — `GET /registered` route untouched.
- All `/unsubscribe` tests — unrelated to this change.
- All `tests/test_registry.py` — DB layer unaffected.
