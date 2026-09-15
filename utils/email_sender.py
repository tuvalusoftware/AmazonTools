"""Shared SMTP sender used by cron jobs and alert notifications."""

from __future__ import annotations

import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from config import settings
from utils.logger import get_logger

log = get_logger(__name__)


def send_email(
    to: str,
    subject: str,
    html_body: str,
    attachment: Path | None = None,
) -> None:
    """Send *html_body* to *to* via configured SMTP settings.

    When *attachment* is provided, the message is wrapped in a
    ``multipart/mixed`` envelope with the HTML as a ``multipart/alternative``
    sub-part and the file attached as ``application/octet-stream``.

    Errors are logged at ERROR level; exceptions are not propagated so
    that a single bad recipient does not abort the caller.
    """
    smtp_cfg = settings.smtp
    from_addr = smtp_cfg.from_addr or smtp_cfg.user

    html_part = MIMEMultipart("alternative")
    html_part.attach(MIMEText(html_body, "html", "utf-8"))

    if attachment is not None:
        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to
        msg.attach(html_part)
        pdf_bytes = attachment.read_bytes()
        pdf_part = MIMEApplication(pdf_bytes, Name=attachment.name)
        pdf_part["Content-Disposition"] = f'attachment; filename="{attachment.name}"'
        msg.attach(pdf_part)
    else:
        msg = html_part
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to

    try:
        if smtp_cfg.port == 465:
            with smtplib.SMTP_SSL(smtp_cfg.host, smtp_cfg.port) as server:
                if smtp_cfg.user and smtp_cfg.password:
                    server.login(smtp_cfg.user, smtp_cfg.password)
                server.sendmail(from_addr, [to], msg.as_string())
        else:
            with smtplib.SMTP(smtp_cfg.host, smtp_cfg.port) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                if smtp_cfg.user and smtp_cfg.password:
                    server.login(smtp_cfg.user, smtp_cfg.password)
                server.sendmail(from_addr, [to], msg.as_string())

        log.info("Email sent to %s", to)

    except smtplib.SMTPException as exc:
        log.error("SMTP error sending to %s: %s", to, exc)
    except Exception as exc:  # noqa: BLE001
        log.error("Unexpected error sending email to %s: %s", to, exc)
