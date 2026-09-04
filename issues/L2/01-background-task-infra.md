# 1. Background task — `RegisterService` in `web/register_service.py`

> Parent overview: [Issue 2 — Async register flow](./main.md)

## What was done

Extracted the full post-submit lifecycle into `web/register_service.py` as a
class rather than a bare function. The class owns ASIN lookup → DB write →
email dispatch and is the only place in the codebase that calls `search_asin`,
`BookRepo`, and `send_email` together.

## Location

`web/register_service.py` — new file, separate from `web/app.py`.

## Class

```python
class RegisterService:
    def __init__(self, email: str, title: str, profit_val: float, price_val: float) -> None: ...

    def run(self) -> None:
        """Single public entry point — called by BackgroundTasks."""
```

`run()` has no return value. All errors are caught and logged; they never
propagate out of the background thread.

## Logic inside `run()`

```
try:
    _, asin = search_asin(self.title)
except (ValueError, RuntimeError):
    log.warning(...)
    send_email(self.email, *self._email_not_found())
    return
except Exception:
    log.warning(...)
    send_email(self.email, *self._email_not_found())
    return

inserted = BookRepo().register_book({...})

if not inserted:
    send_email(self.email, *self._email_duplicate(asin))
    return

send_email(self.email, *self._email_confirmed(asin))
```

## Edge cases

- `search_asin` raises `ValueError` **or** `RuntimeError` — both treated as
  "not found": log at WARNING, send not-found email.
- Any other exception — same fallback (broad `except` with `# noqa: BLE001`).
- `send_email` never raises — no extra try/except needed around email calls.
- `BookRepo().register_book` returns `False` for a duplicate `(email, asin)`
  pair — this is the "already tracking" branch.

## Impact on `web/app.py`

- Removed `_resolve_and_notify`, all three `_email_*` helpers, and the
  `settings`, `send_email`, `search_asin`, `quote` imports.
- Route enqueues: `background_tasks.add_task(RegisterService(...).run)`.
