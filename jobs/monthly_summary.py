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


def _months_between(start: tuple[int, int], end: tuple[int, int]) -> list[tuple[int, int]]:
    """Inclusive list of (year, month) tuples from start to end, both inclusive."""
    months = []
    y, m = start
    while (y, m) <= end:
        months.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return months


def _resolve_profit_pct(book_repo: BookRepo, asin: str) -> float:
    book_row = book_repo.find_book_by_asin(asin)
    if book_row is None:
        return _DEFAULT_PROFIT_PCT
    raw_pct = book_row.get("profit_pct")
    return float(raw_pct) if isinstance(raw_pct, (int, float)) and raw_pct else _DEFAULT_PROFIT_PCT


def sync_missing_months(
    asin: str,
    *,
    snapshot_repo: SnapshotRepo | None = None,
    book_repo: BookRepo | None = None,
    summary_repo: MonthlySummaryRepo | None = None,
) -> int:
    """Compute and store every completed calendar month missing a summary
    row for *asin*, from its earliest snapshot up to last month.

    Cheap no-op when already up to date: a normal call (nothing missed)
    does exactly one `get_data_month_range` + a handful of indexed
    `MonthlySummaryRepo.get()` lookups, no `save()`. Safe to call once per
    ASIN per scrape, every day.

    Returns the number of months computed (0 if nothing was missing).
    """
    snapshot_repo = snapshot_repo or SnapshotRepo()
    book_repo = book_repo or BookRepo()
    summary_repo = summary_repo or MonthlySummaryRepo()

    data_range = snapshot_repo.get_data_month_range(asin)
    if data_range is None:
        return 0

    start_y, start_m, end_y, end_m = data_range
    last_complete = _target_month()
    end = min((end_y, end_m), last_complete)  # never touch the in-progress current month

    computed = 0
    for year, month in _months_between((start_y, start_m), end):
        if summary_repo.get(asin, year, month) is not None:
            continue  # already computed — normal case for every month but a genuine gap

        rows = snapshot_repo.load_daily_snapshots_for_month(asin, year, month)
        if not rows:
            continue  # ASIN had no data that particular month (e.g. added mid-range)

        profit_pct = _resolve_profit_pct(book_repo, asin)
        total_units, total_profit, days_with_data = aggregate_month(rows, profit_pct)
        summary_repo.save(asin, year, month, total_units, total_profit, days_with_data)
        computed += 1

    return computed


def run() -> None:
    """Monthly cron entry point — self-heals every ASIN with any snapshot
    history (active or not). Complements the per-ASIN call from
    jobs/scrape_bsr.py, which only covers active ASINs but runs daily."""
    snapshot_repo = SnapshotRepo()
    book_repo = BookRepo()
    summary_repo = MonthlySummaryRepo()

    asins = snapshot_repo.list_asins_that_have_data()
    total_computed = 0
    for asin in asins:
        total_computed += sync_missing_months(
            asin, snapshot_repo=snapshot_repo, book_repo=book_repo, summary_repo=summary_repo,
        )

    log.info(
        "Monthly summary cron: %d month(s) computed across %d ASIN(s)",
        total_computed, len(asins),
    )
