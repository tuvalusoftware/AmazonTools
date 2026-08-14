# PLAN-001 — C007: Switch Email Transport to Gmail SMTP

← [plan001.main.md](plan001.main.md)

Replaces the SendGrid SMTP relay with Gmail SMTP (direct, using a Google App Password).
SendGrid's free trial expired (Aug 4 2026); Gmail SMTP works immediately with no paid plan and
no domain ownership required.

**Depends on:** [plan001.C003_EmailDigest.todo.md](plan001.C003_EmailDigest.todo.md)

---

## Why Gmail instead of SendGrid

| Reason | Detail |
|---|---|
| SendGrid trial expired | Aug 4 2026 — all SMTP connections are rejected (`Connection unexpectedly closed`) |
| No custom domain | SendGrid Domain Authentication requires owning a domain; Single Sender Verification works but is only available on paid plans after trial end |
| Gmail SMTP is free | 500 emails/day with a Google App Password; sufficient for the daily digest use-case |
| Zero code change | `send_email()` already uses `smtplib`; only `.env` values change |

---

## Prerequisites (manual, one-time)

- [ ] Enable 2-Step Verification on `leanhkhoi2611@gmail.com` (required by Google):
  [https://myaccount.google.com/security](https://myaccount.google.com/security)
- [ ] Create a Google App Password:
  [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
  → App name: `bsr-tracker` → copy the 16-character password (format: `xxxx xxxx xxxx xxxx`)

---

## `config.py` — clean up SendGrid field

- [x] Remove the `SENDGRID_API_KEY` field and `effective_smtp` property from `Settings`
  — Gmail credentials are set directly via `SMTP__*` env vars; no relay shim needed
- [x] Remove the `effective_smtp` property call in `jobs/email_digest.py`
  — revert `send_email()` to use `settings.smtp` directly

---

## `.env` — update SMTP credentials

- [x] Set `SMTP__HOST=smtp.gmail.com`
- [x] Set `SMTP__PORT=587`
- [x] Set `SMTP__USER=leanhkhoi2611@gmail.com`
- [x] Set `SMTP__PASSWORD=<16-char app password>`  ← paste App Password here
- [x] Set `SMTP__FROM_ADDR=leanhkhoi2611@gmail.com`
- [x] Clear `SENDGRID_API_KEY=` (leave blank or remove the line)

---

## `.env.example` — update documentation

- [x] Replace SendGrid block with Gmail instructions:
  ```
  # Gmail SMTP — create an App Password at https://myaccount.google.com/apppasswords
  # Requires 2-Step Verification to be enabled on the sending account.
  SMTP__HOST=smtp.gmail.com
  SMTP__PORT=587
  SMTP__USER=your_email@gmail.com
  SMTP__PASSWORD=xxxx xxxx xxxx xxxx   # 16-char Google App Password
  SMTP__FROM_ADDR=your_email@gmail.com
  ```
- [x] Remove `SENDGRID_API_KEY` entry from `.env.example`

---

## Verification

- [x] Run the debug snippet to confirm login succeeds:
  ```bash
  python -c "
  import smtplib
  from config import settings
  cfg = settings.smtp
  with smtplib.SMTP(cfg.host, cfg.port) as s:
      s.ehlo(); s.starttls(); s.ehlo()
      print('LOGIN:', s.login(cfg.user, cfg.password))
  "
  ```
- [x] Run the integration test — confirm `PASSED` with no ERROR log:
  ```bash
  pytest tests/integration/test_email_digest_integration.py::test_send_digest_email_real -m integration -v -s
  ```
- [x] Check inbox at `leanhkhoi2611@gmail.com` — confirm email arrived with correct subject and book data
- [ ] Confirm no exception propagates when `SMTP__PASSWORD` is wrong — only ERROR log emitted
