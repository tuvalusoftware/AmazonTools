# Email Setup — qmodeler.net

Audience: **Admin** managing the `qmodeler.net` domain and Google Workspace.

Goal: create a dedicated sending mailbox (e.g. `noreply@qmodeler.net`) and an
App Password, so the app can send digest emails via SMTP. Once done, send the
**"Send to Dev"** section below to the dev over a private channel (password
manager or encrypted DM — not plain chat or email).

## Steps (Admin)

1. **Create the sending mailbox in Google Workspace**
   Create a new user, e.g. `noreply@qmodeler.net`, dedicated to automated
   sending — do not reuse a personal mailbox.
   Where: `admin.google.com` → Directory → Users

2. **Enable 2-Step Verification on that account**
   An App Password can only be created once 2-Step Verification is on.
   Where: `myaccount.google.com` → Security → 2-Step Verification

3. **Create an App Password**
   Sign in as `noreply@qmodeler.net`, create an App Password of type
   "Mail" / "Other". Google shows a 16-character string once — copy it
   immediately.
   Where: `myaccount.google.com/apppasswords`

4. **Add an SPF record for the domain**
   Authorizes Gmail to send on behalf of `qmodeler.net`, so outgoing mail
   isn't flagged as spam. Add the TXT record below at the domain's DNS
   provider.

5. **Send the config to dev**
   Copy the env block below, fill in the App Password, and send it to the
   dev over a private channel.

## DNS records to add

Add these at the DNS zone for `qmodeler.net`. If the domain already uses
Google Workspace for receiving mail (MX records set up), only the SPF line
below is needed.

| Type | Host     | Value                                             | TTL  |
|------|----------|----------------------------------------------------|------|
| TXT  | `@`      | `v=spf1 include:_spf.google.com ~all`               | 3600 |
| TXT (recommended) | `_dmarc` | `v=DMARC1; p=none; rua=mailto:admin@qmodeler.net` | 3600 |

> **Important:** if `qmodeler.net` already has another `v=spf1 …` TXT record
> (e.g. from Mailchimp or SendGrid), **do not add a second one** — merge
> `include:_spf.google.com` into the existing record instead. Multiple SPF
> records make the whole SPF check invalid.

## Send to Dev

Fill in the placeholders and hand this block to the dev — it goes straight
into the project's `.env` file.

```env
# Google Workspace — qmodeler.net sending mailbox
SMTP__HOST=smtp.gmail.com
SMTP__PORT=587
SMTP__USER=noreply@qmodeler.net
SMTP__PASSWORD=<16-character App Password, no spaces>
SMTP__FROM_ADDR=noreply@qmodeler.net
```

`SMTP__PASSWORD` is the App Password from step 3 — **not** the login
password for `noreply@qmodeler.net`.
