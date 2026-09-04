# 4. Email digest run — verify email + PDF attachment

Precondition: [03-scrape-flow.md](./03-scrape-flow.md) done — at least one
row in `bsr_snapshots` for your registered book(s).

## Trigger a digest run manually

In the same second terminal as step 3:

- [ ] Run `make run-job` and choose option **2) Email digest job** when
      prompted (`scripts/run_job.py` runs `jobs.email_digest.run()` — same
      job the cron scheduler fires, on demand).
  - Tip: option **3) Both** runs the scrape job immediately followed by the
    digest job in one go — useful once you've already validated each stage
    separately in steps 3 and 4.
  - Expected log lines: `PDF generated at <tmp path>`, `Digest email sent
    to <your email>` (once per unique registered email), `Digest run
    complete — emailed N author(s).`.
  - If you see `PDF generation failed — sending email without attachment:
    ...` instead, note the exception text — the email should still arrive,
    just without the PDF (this is intentional degraded behavior per the
    code, not a hard failure — but worth flagging so the PDF path gets
    fixed).

## Verify the email

- [ ] Check the inbox for the email you registered with (check Spam too).
  - Expected subject: `📚 Daily BSR Digest — <today's date>`.
  - Expected body: your book title(s), a formatted rank (e.g. `#1,523`),
    the category, and your profit % context.
  - Expected: a PDF attachment named `bsr_report_<today>.pdf` (unless the
    log showed the PDF-generation failure above).
  - Expected: each book row has an **"Unsubscribe this book"** link, and
    the footer has an **"Unsubscribe all"** link.

## Verify the PDF attachment

- [ ] Open the PDF attachment.
  - Expected: it opens without error/corruption and shows the registered
    book(s) with their latest BSR/price data — cross-check the rank/price
    numbers against what you recorded from the `bsr_snapshots` query in
    step 3.

## No-active-books edge case

- [ ] Temporarily unsubscribe all your test books (see
      [05-unsubscribe-and-edge-cases.md](./05-unsubscribe-and-edge-cases.md)),
      then re-run `make run-job` choosing option **2** again.
  - Expected log line: `No active books found — skipping digest email
    run.` — no email sent, no crash.
  - Re-register a book afterward if you plan to continue testing.
