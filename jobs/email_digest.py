"""
Email digest job — builds and sends a per-author HTML email summarising
BSR ranks for all active tracked books.

Entry point:
    python -c "from jobs.email_digest import run; run()"
"""

from __future__ import annotations

import smtplib
import tempfile
from collections import defaultdict
from datetime import date
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from urllib.parse import quote

from jinja2 import Environment, FileSystemLoader

from config import settings
from reports.Service_pdf_genFromAsin import Service_Pdf_GenFromAsin
from utils.Formula_calculator import Formula
from utils.logger import get_logger
from utils.registry import BookRepo

log = get_logger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


# ------------------------------------------------------------------ #
# Email builder                                                        #
# ------------------------------------------------------------------ #

def _build_digest_html(email: str, books: list[dict]) -> str:
    """Render the digest template for *email* and its tracked *books*.

    Each item in *books* must be a plain dict from ``load_active_books``
    with at least: asin, title, profit_pct, current_price.
    """
    repo = BookRepo()
    book_contexts: list[dict] = []

    for book in books:
        asin: str = book["asin"]
        snapshot = repo.load_latest_snapshot(asin)

        current_rank: int | None = int(snapshot["rank"]) if snapshot else None  # type: ignore[arg-type]
        category: str = str(snapshot["category"]) if snapshot else ""

        profit_pct: float = float(book["profit_pct"])  # type: ignore[arg-type]
        # Price comes from the latest BSR snapshot; fall back to the seed value
        # in tracked_books (0.0) if no snapshot exists yet.
        current_price: float = (
            float(snapshot["price"])  # type: ignore[arg-type]
            if snapshot and snapshot.get("price")
            else float(book["current_price"])  # type: ignore[arg-type]
        )
        estimated_daily_profit: float | None = (
            Formula.daily_profit(current_rank, current_price, profit_pct)
            if current_rank is not None
            else None
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
    that a single bad recipient does not abort the digest run.
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

    pdf_filename = f"bsr_report_{today}.pdf"
    tmp_pdf: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".pdf", prefix="bsr_report_", delete=False
        ) as tmp_f:
            tmp_pdf = Path(tmp_f.name)

        Service_Pdf_GenFromAsin(asin_filter=None, output_path=tmp_pdf).run()
        tmp_pdf = tmp_pdf.rename(tmp_pdf.with_name(pdf_filename))
        log.info("PDF generated at %s", tmp_pdf)
    except Exception as exc:  # noqa: BLE001
        log.error("PDF generation failed — sending email without attachment: %s", exc)
        tmp_pdf = None

    authors_emailed = 0
    for email_addr, books in grouped.items():
        html = _build_digest_html(email_addr, books)
        send_email(email_addr, subject, html, attachment=tmp_pdf)
        authors_emailed += 1

    if tmp_pdf is not None and tmp_pdf.exists():
        tmp_pdf.unlink()
        log.debug("Temp PDF deleted: %s", tmp_pdf)

    log.info("Digest run complete — emailed %d author(s).", authors_emailed)
