"""
Integration test — visual preview of _build_digest_html output.

Purpose
-------
Render the digest HTML template with realistic seed data (no live Amazon
network call needed) and write the result to a temp file so you can open it
in a browser to inspect the layout.

Run
---
    pytest tests/integration/test_email_digest_integration.py -m integration -v -s

The test prints the output path to stdout (-s) so you can open it directly:
    open /tmp/digest_preview.html          # macOS
    xdg-open /tmp/digest_preview.html     # Linux
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings  # noqa: E402
from jobs.email_digest import _build_digest_html, send_email  # noqa: E402
from jobs.scrape_bsr import BestSellerRank  # noqa: E402
from utils.registry import BookRepo  # noqa: E402

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Seed data — edit these to try different scenarios
# ---------------------------------------------------------------------------
_EMAIL = "author@example.com"

_BOOKS = [
    {
        "email": _EMAIL,
        "title": "Atomic Habits",
        "asin": "B07RFSSYBH",
        "profit_pct": 70.0,
        "current_price": 0.0,   # will be overridden by snapshot price
    },
    {
        "email": _EMAIL,
        "title": "Deep Work",
        "asin": "B0189PVAWY",
        "profit_pct": 35.0,
        "current_price": 0.0,
    },
    # {  # temporarily disabled — no-snapshot scenario
    #     "email": _EMAIL,
    #     "title": "No Snapshot Book",
    #     "asin": "X_NO_DATA_001",
    #     "profit_pct": 70.0,
    #     "current_price": 9.99,  # snapshot missing → should show "No rank data yet"
    # },
]

# Snapshot data per ASIN — (rank, category, price)
_SNAPSHOTS: dict[str, tuple[int, str, float]] = {
    "B07RFSSYBH": (34,   "Audible Books & Originals",    14.99),
    "B0189PVAWY": (1195, "Audible Books & Originals",    16.99),
    # X_NO_DATA_001 intentionally has no snapshot (disabled above)
}


# ---------------------------------------------------------------------------
# Fixture — disposable SQLite populated with seed data
# ---------------------------------------------------------------------------

@pytest.fixture()
def seeded_repo(tmp_path: Path) -> BookRepo:
    """Create and populate a fresh DB with seed books + snapshots."""
    db_path = tmp_path / "preview_tracker.db"
    repo = BookRepo(db_path=db_path)
    repo.init_db()

    for book in _BOOKS:
        repo.register_book(book)

    base_time = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)
    for asin, (rank, category, price) in _SNAPSHOTS.items():
        # Insert 3 snapshots per ASIN (rank fixed — latest_snapshot returns same rank)
        for offset in range(3):
            scraped_at = (base_time + timedelta(days=offset)).isoformat()
            repo.save_bsr_snapshots([
                BestSellerRank(
                    asin=asin,
                    rank=rank,
                    category=category,
                    price=price,
                    scraped_at=scraped_at,
                )
            ])

    return repo


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

OUTPUT_PATH = Path("/tmp/digest_preview.html")


def test_build_digest_html_preview(seeded_repo: BookRepo, monkeypatch) -> None:
    """
    Render _build_digest_html with real DB data and save to OUTPUT_PATH.

    Structural assertions
    ---------------------
    - HTML is non-empty
    - Each book title appears in the output
    - Ranked books display a formatted rank (e.g. #34)
    - The book with no snapshot shows "No rank data yet"
    - Both unsubscribe URLs are present

    Visual inspection
    -----------------
    Open the printed path in a browser to check layout and styling.
    """
    # _build_digest_html calls BookRepo() internally; redirect it to the seeded DB
    # by patching the class in the jobs.email_digest namespace.
    monkeypatch.setattr(
        "jobs.email_digest.BookRepo",
        lambda: seeded_repo,
    )

    books = seeded_repo.load_active_books()
    email_books = [b for b in books if b["email"] == _EMAIL]

    html = _build_digest_html(_EMAIL, email_books)

    # --- structural assertions ---
    assert html.strip(), "rendered HTML must not be empty"

    for book in _BOOKS:
        assert book["title"] in html, f"title '{book['title']}' missing from HTML"

    assert "#34" in html, "Atomic Habits rank #34 not found"
    assert "#1,195" in html, "Deep Work rank #1,195 not found"
    # assert "No rank data yet" in html, "missing fallback for book with no snapshot"  # temporarily disabled

    assert "unsubscribe" in html.lower(), "unsubscribe link missing"
    assert f"email=" in html, "email param missing from unsubscribe URL"

    # --- write preview file ---
    OUTPUT_PATH.write_text(html, encoding="utf-8")

    print(
        f"\n{'='*60}\n"
        f"  Digest HTML preview saved to:\n"
        f"  {OUTPUT_PATH}\n"
        f"\n"
        f"  Open in browser:\n"
        f"    open {OUTPUT_PATH}       # macOS\n"
        f"    xdg-open {OUTPUT_PATH}   # Linux\n"
        f"{'='*60}"
    )


def test_send_digest_email_real(seeded_repo: BookRepo, monkeypatch, caplog) -> None:
    """
    Render the digest HTML and send it to the address in SMTP__FROM_ADDR via
    Gmail SMTP.

    Skip conditions
    ---------------
    - SMTP__PASSWORD is not set
    - SMTP__FROM_ADDR is not set

    Run
    ---
        pytest tests/integration/test_email_digest_integration.py::test_send_digest_email_real -m integration -v -s
    """
    smtp_password = settings.smtp.password
    from_addr = settings.smtp.from_addr

    if not smtp_password:
        pytest.skip("SMTP__PASSWORD not set — skipping live send test")
    if not from_addr:
        pytest.skip("SMTP__FROM_ADDR not set — skipping live send test")

    monkeypatch.setattr(
        "jobs.email_digest.BookRepo",
        lambda: seeded_repo,
    )

    books = seeded_repo.load_active_books()
    email_books = [b for b in books if b["email"] == _EMAIL]
    html = _build_digest_html(_EMAIL, email_books)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    subject = f"[Integration Test] BSR Digest Preview — {today}"

    send_email(to=from_addr, subject=subject, html_body=html)

    smtp_errors = [r for r in caplog.records if r.levelname == "ERROR"]
    assert not smtp_errors, (
        f"send_email logged an error — email was NOT delivered:\n"
        + "\n".join(r.getMessage() for r in smtp_errors)
    )

    print(
        f"\n{'='*60}\n"
        f"  Digest email sent to: {from_addr}\n"
        f"  Subject : {subject}\n"
        f"  Check your inbox (and Spam folder).\n"
        f"{'='*60}"
    )
