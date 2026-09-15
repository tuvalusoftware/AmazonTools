# 2. Register a book through the Web UI

Precondition: [01-preconditions.md](./01-preconditions.md) fully checked,
`make start` running.

> **Async flow (as of Issue 2):** clicking Register never blocks. The route
> returns `pending.html` in < 1 s; ASIN lookup + DB write + email all happen
> in a background thread. You verify success by checking your inbox and then
> SQLite — not by what the browser shows immediately.

## Happy path

- [x] On `http://localhost:<WEB_PORT>/`, fill the form:
  - Email: a real inbox you can check (this is where both the registration
    confirmation and future digests will be sent).
  - Book title: a well-known title Amazon reliably resolves, e.g.
    `Theo of Golden: A Novel`.
  - Profit %: any value between 0 and 100, e.g. `50`.
  - Current price: any non-negative number, e.g. `0` (this is a fallback
    only — the real price is scraped later).
- [x] Click **Register** (or the form's submit button).
  - Expected: the page switches **immediately** (< 1 s) to the amber
    "We've received your request" pending page (`/pending`). No blocking
    wait.
- [x] Wait up to ~1 minute for the confirmation email to arrive in your
  ```
  inbox (check Spam too).
  ```

  - Expected subject: `Your book "Theo of Golden: A Novel" has been registered`
  - Expected body: book title, resolved ASIN, note that BSR/price tracking
    is now active, digest schedule, and an unsubscribe link.
  - Record the ASIN shown in the email — steps 3 and 4 will refer to it.

## Verify persistence

- [x] Inspect the SQLite DB directly:
  ```
  `sqlite3 data/tracker.db "SELECT email, title, asin, profit_pct, current_price, active FROM tracked_books;"`
  ```

  - Expected: one row with your email/title, `active = 1`, and a non-empty
    `asin` (10-character Amazon ASIN, e.g. `B07RFSSYBH`).

## Error path — unresolvable title

- [x] Repeat the form submission with an obviously nonsense title, e.g.
  ```
  `zzzzz_no_such_book_qxqxqx`.
  ```

  - Expected: the browser **immediately** shows the pending page — same as
    happy path (the route does not know the lookup result yet).
  - Wait up to ~1 minute for a "not found" email:
    - Expected subject: `We could not find your book on Amazon`
    - Expected body: echoes the title you entered; invites re-submit with a
      tip to use the exact Amazon title.
  - Confirm via
    `sqlite3 data/tracker.db "SELECT COUNT(*) FROM tracked_books;"`
    that the count did **not** increase (no row inserted on lookup failure).

## Error path — duplicate registration

- [x] Submit the same email + title from the happy-path step again.
  - Expected: pending page immediately, followed by an "already tracking"
    email within ~1 minute:
    - Expected subject: `You are already tracking "Theo of Golden: A Novel"`
    - Expected body: confirms book is already active, no changes made,
      includes an unsubscribe link.
  - Confirm via SQLite that no duplicate row was inserted.

## Error path — invalid form values (client-side validation)

- [x] Submit with profit % = `150` (out of 0–100 range).
  - Expected: error "Profit % must be a number between 0 and 100."
    — form re-renders, no pending page, no email.
- [x] Submit with current price = `-5` (negative).
  - Expected: error "Book price must be a non-negative number."
- [x] Submit with empty email or a value with no `@`.
  - Expected: error "Please enter a valid email address."
