"""
Email digest job — builds and sends a per-author HTML email summarising
BSR ranks for all active tracked books.

Entry point:
    python -c "from jobs.email_digest import run; run()"
"""

from __future__ import annotations

import tempfile
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote

from jinja2 import Environment, FileSystemLoader

from config import settings
from reports.Service_pdf_genFromAsin import Service_Pdf_GenFromAsin
from utils.email_sender import send_email
from utils.Formula_calculator import Formula
from utils.logger import get_logger
from utils.registry import BookRepo
from utils.Repo_CronRunLog import CronRunLogRepo

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
# Per-subscriber PDF                                                   #
# ------------------------------------------------------------------ #

def _build_user_pdf(asins: list[str], today: str) -> Path | None:
    """Generate a BSR report PDF containing only *asins*.

    Returns the path to the written file (named ``bsr_report_<today>.pdf``),
    or ``None`` if generation failed or no book had enough snapshot data.
    The caller is responsible for deleting the returned file.
    """
    if not asins:
        return None

    pdf_filename = f"bsr_report_{today}.pdf"
    tmp_pdf: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".pdf", prefix="bsr_report_", delete=False
        ) as tmp_f:
            tmp_pdf = Path(tmp_f.name)

        generated = Service_Pdf_GenFromAsin(
            asin_filter=asins, output_path=tmp_pdf
        ).run()
        if generated is None:
            log.info("No followed books had enough snapshot data yet — email without PDF")
            tmp_pdf.unlink(missing_ok=True)
            return None

        renamed = tmp_pdf.rename(tmp_pdf.with_name(pdf_filename))
        log.info("PDF generated at %s", renamed)
        return renamed
    except Exception as exc:  # noqa: BLE001
        log.error("PDF generation failed — sending email without attachment: %s", exc)
        if tmp_pdf is not None:
            tmp_pdf.unlink(missing_ok=True)
        return None


# ------------------------------------------------------------------ #
# Job entry point                                                      #
# ------------------------------------------------------------------ #

def run() -> None:
    """Build and dispatch one digest email per unique author address."""
    started_at = datetime.now(timezone.utc).isoformat()
    repo = BookRepo()
    active_books = repo.load_active_books()

    if not active_books:
        log.warning("No active books found — skipping digest email run.")
        _log_cron_run(
            started_at=started_at,
            status="success",
            detail="no active books — skipped",
        )
        return

    grouped: dict[str, list[dict]] = defaultdict(list)
    for book in active_books:
        grouped[str(book["email"])].append(book)

    today = date.today().strftime("%Y-%m-%d")
    subject = f"\U0001f4da Weekly BSR Digest \u2014 {today}"

    authors_emailed = 0
    for email_addr, books in grouped.items():
        html = _build_digest_html(email_addr, books)
        # Build a PDF scoped to just the books this subscriber follows, so no
        # subscriber ever receives BSR data about another subscriber's books.
        followed_asins = [str(book["asin"]) for book in books]
        tmp_pdf = _build_user_pdf(followed_asins, today)
        try:
            send_email(email_addr, subject, html, attachment=tmp_pdf)
        finally:
            if tmp_pdf is not None and tmp_pdf.exists():
                tmp_pdf.unlink()
                log.debug("Temp PDF deleted: %s", tmp_pdf)
        authors_emailed += 1

    log.info("Digest run complete — emailed %d author(s).", authors_emailed)
    _log_cron_run(
        started_at=started_at,
        status="success",
        detail=f"{authors_emailed} author(s) emailed",
    )


def _log_cron_run(*, started_at: str, status: str, detail: str | None) -> None:
    """Write one cron_run_log row without letting a logging failure abort the run."""
    try:
        CronRunLogRepo().save(
            "email_digest",
            asin=None,
            trigger="cron",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc).isoformat(),
            status=status,
            detail=detail,
        )
    except Exception as exc:
        log.warning("Failed to write cron_run_log row for email_digest: %s", exc)
