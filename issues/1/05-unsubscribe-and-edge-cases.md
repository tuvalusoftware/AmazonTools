# 5. Unsubscribe flow + negative/edge cases

Precondition: at least one registered, active book with a digest email
already received (steps 2–4 done at least once), so you have real
unsubscribe links to click.

## Unsubscribe a single book (from the email link)

- [ ] In the digest email received in step 4, click **"Unsubscribe this
      book"** next to one book.
  - Expected: browser opens `/unsubscribe?email=<email>&asin=<asin>` and
    shows a confirmation page naming the book title.
- [ ] Verify in SQLite:
      `sqlite3 data/tracker.db "SELECT title, active FROM tracked_books WHERE asin = '<that asin>';"`
  - Expected: `active = 0`. The row is **retained**, not deleted.
- [ ] Re-run `make run-job` choosing option **1** (scrape) and then option
      **2** (digest) from step 4.
  - Expected: the unsubscribed book is skipped by both — no new snapshot,
    no mention in the email.

## Unsubscribe all books for an email

- [ ] Click the footer **"Unsubscribe all"** link in an email (or navigate
      to `/unsubscribe?email=<your email>` directly).
  - Expected: confirmation page shows a count of books unsubscribed.
- [ ] Verify: `sqlite3 data/tracker.db "SELECT title, active FROM tracked_books WHERE email = '<your email>';"`
  - Expected: all rows for that email now have `active = 0`.

## Unsubscribe edge cases

- [ ] Visit `/unsubscribe?email=<email that was never registered>`.
  - Expected: confirmation page in "not found" mode — no error/crash.
- [ ] Visit `/unsubscribe?email=<already-unsubscribed email>&asin=<already-unsubscribed asin>` again (click the same link twice).
  - Expected: still resolves to "not found" mode (already inactive) rather
    than throwing — confirms `unsubscribe_book`/`unsubscribe_email` are
    idempotent from the user's perspective.

## Wrap-up

- [ ] Re-register at least one book (repeat
      [02-register-flow.md](./02-register-flow.md) happy path, including
      waiting for the confirmation email) if you want the app left in a
      "has active data" state for the next person running this checklist,
      or leave it clean if the DB was backed up/reset in step 1.
- [ ] Record final pass/fail summary for the whole checklist (1–5) — any
      unchecked box or unexpected result should be filed as its own bug
      referencing this issue.
