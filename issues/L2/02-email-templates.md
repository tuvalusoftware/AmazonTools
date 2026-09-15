# 2. Email templates for registration outcomes

> Parent overview: [Issue 2 — Async register flow](./main.md)

## What was done

Three private builder methods live on `RegisterService` in
`web/register_service.py` (not in `web/app.py`). Each returns
`(subject, html_body)` and is called from `RegisterService.run()`.

## Methods

```python
def _email_confirmed(self, asin: str) -> tuple[str, str]: ...
def _email_not_found(self)            -> tuple[str, str]: ...
def _email_duplicate(self, asin: str) -> tuple[str, str]: ...
```

`self.email` and `self.title` are accessed from instance state; `asin` is
passed in because it is only known after a successful lookup.

## Template A — Registration confirmed

Subject: `Your book "{title}" has been registered`

Key content:
- Book title and resolved ASIN.
- Confirmation that BSR/price tracking is now active.
- Digest schedule: derived at runtime from `settings.EMAIL_DIGEST_CRON` and `settings.TIMEZONE` via `_digest_schedule_label()` — never hardcoded.
- Unsubscribe link: `{settings.WEB_BASE_URL}/unsubscribe?email={email}&asin={asin}`

## Template B — Book not found

Subject: `We could not find your book on Amazon`

Key content:
- Echo the title the user entered.
- Invite re-submit via `settings.WEB_BASE_URL` with a tip to use the exact Amazon title.

## Template C — Already tracking

Subject: `You are already tracking "{title}"`

Key content:
- Confirm book is already active, no changes made.
- Unsubscribe link as in Template A.
