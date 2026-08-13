"""
Email digest job — builds and sends a per-author HTML email summarising
BSR ranks for all active tracked books.

Entry point:
    python -c "from jobs.email_digest import run; run()"
"""

from __future__ import annotations

import smtplib
from collections import defaultdict
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from urllib.parse import quote

from jinja2 import Environment, FileSystemLoader

from config import settings
from utils.logger import get_logger
from utils.registry import BookRepo

log = get_logger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


# ------------------------------------------------------------------ #
# Email builder                                                        #
# ------------------------------------------------------------------ #

def build_digest_html(email: str, books: list[dict]) -> str:
    """Render the digest template for *email* and its tracked *books*.

    Each item in *books* must be a plain dict from ``load_active_books``
    with at least: asin, title, profit_pct, current_price.
    """
    repo = BookRepo()
    book_contexts: list[dict] = []

    for book in books:
        asin: str = book["asin"]
        snapshot = repo.load_latest_snapshot(asin)
        trend = repo.load_rank_history(asin, days=7)

        current_rank = snapshot["rank"] if snapshot else None
        category = snapshot["category"] if snapshot else ""

        profit_pct: float = float(book["profit_pct"])
        # Price comes from the latest BSR snapshot; fall back to the seed value
        # in tracked_books (0.0) if no snapshot exists yet.
        current_price: float = (
            float(snapshot["price"])
            if snapshot and snapshot.get("price")
            else float(book["current_price"])
        )
        estimated_daily_profit: float | None = (
            current_price * (profit_pct / 100.0) if current_rank is not None else None
        )

        unsubscribe_book_url = (
            f"{settings.WEB_BASE_URL}/unsubscribe"
            f"?email={quote(email)}&asin={quote(asin)}"
        )

        book_contexts.append(
            {
                "title": book["title"],
                "asin": asin,
                "current_rank": current_rank,
                "category": category,
                "trend": trend,
                "profit_pct": profit_pct,
                "current_price": current_price,
                "estimated_daily_profit": estimated_daily_profit,
                "unsubscribe_book_url": unsubscribe_book_url,
            }
        )

    unsubscribe_all_url = (
        f"{settings.WEB_BASE_URL}/unsubscribe?email={quote(email)}"
    )

    env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)
    template = env.get_template("digest.html")
    return template.render(
        email=email,
        books=book_contexts,
        unsubscribe_all_url=unsubscribe_all_url,
    )


# ------------------------------------------------------------------ #
# SMTP sender                                                          #
# ------------------------------------------------------------------ #

def send_email(to: str, subject: str, html_body: str) -> None:
    """Send *html_body* to *to* via configured SMTP settings.

    Errors are logged at ERROR level; exceptions are not propagated so
    that a single bad recipient does not abort the digest run.
    """
    smtp_cfg = settings.smtp
    from_addr = smtp_cfg.from_addr or smtp_cfg.user

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to
    msg.attach(MIMEText(html_body, "html", "utf-8"))

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

        log.info("Digest email sent to %s", to)

    except smtplib.SMTPException as exc:
        log.error("SMTP error sending to %s: %s", to, exc)
    except Exception as exc:  # noqa: BLE001
        log.error("Unexpected error sending email to %s: %s", to, exc)


# ------------------------------------------------------------------ #
# Job entry point                                                      #
# ------------------------------------------------------------------ #

def run() -> None:
    """Build and dispatch one digest email per unique author address."""
    repo = BookRepo()
    active_books = repo.load_active_books()

    if not active_books:
        log.warning("No active books found — skipping digest email run.")
        return

    grouped: dict[str, list[dict]] = defaultdict(list)
    for book in active_books:
        grouped[str(book["email"])].append(book)

    today = date.today().strftime("%Y-%m-%d")
    subject = f"\U0001f4da Daily BSR Digest \u2014 {today}"

    authors_emailed = 0
    for email_addr, books in grouped.items():
        html = build_digest_html(email_addr, books)
        send_email(email_addr, subject, html)
        authors_emailed += 1

    log.info("Digest run complete — emailed %d author(s).", authors_emailed)
