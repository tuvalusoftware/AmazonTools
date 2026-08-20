"""
Monthly summary job — precomputes the just-completed calendar month's
profit summary for every ASIN with any snapshot history.

Entry point:
    python -c "from jobs.monthly_summary import run; run()"
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from config import settings
from reports.Helper_Pdf_Loader import _DEFAULT_PROFIT_PCT
from reports.Helper_Pdf_Metrics import aggregate_month
from utils.logger import get_logger
from utils.registry import BookRepo
from utils.Repo_MonthlySummary import MonthlySummaryRepo
from utils.Repo_Snapshot import SnapshotRepo

log = get_logger(__name__)


def _target_month() -> tuple[int, int]:
    """Return (year, month) for the calendar month before today, in settings.TIMEZONE."""
    today = datetime.now(ZoneInfo(settings.TIMEZONE)).date()
    year, month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    return year, month


def run() -> None:
    """Compute and persist the previous calendar month's profit summary
    for every ASIN that has any snapshot history (active or not)."""
    year, month = _target_month()

    snapshot_repo = SnapshotRepo()
    book_repo = BookRepo()
    summary_repo = MonthlySummaryRepo()

    asins = snapshot_repo.list_asins_that_have_data()
    count = 0

    for asin in asins:
        rows = snapshot_repo.load_daily_snapshots_for_month(asin, year, month)
        if not rows:
            continue

        book_row = book_repo.find_book_by_asin(asin)
        if book_row is not None:
            raw_pct = book_row.get("profit_pct")
            profit_pct = float(raw_pct) if isinstance(raw_pct, (int, float)) and raw_pct else _DEFAULT_PROFIT_PCT
        else:
            profit_pct = _DEFAULT_PROFIT_PCT

        total_units, total_profit, days_with_data = aggregate_month(rows, profit_pct)
        summary_repo.save(asin, year, month, total_units, total_profit, days_with_data)
        count += 1

    log.info("Monthly summary computed for %d ASIN(s) — %04d-%02d", count, year, month)
