"""
Retry ASINs whose latest scrape_bsr cron run today failed.

Selection: for each active ASIN in tracked_books, look at its most recent
cron_run_log row with cron_type='scrape_bsr' and started_at falling on
"today" in settings.TIMEZONE. Only ASINs whose latest such row has
status='failure' are retried — an ASIN that failed earlier today but has
since succeeded is left alone, and failures from a prior day are ignored.

Each retried ASIN follows the same flow as jobs.scrape_bsr.run():
_scrape_bsr -> save snapshot -> sync_missing_months -> write cron_run_log
rows, using trigger='manual' to distinguish these rows from the scheduled
cron run.

Usage:
    python -m scripts.retry_failed_scrapes
    make retry-failed
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from datetime import time as dt_time
from zoneinfo import ZoneInfo

from config import settings
from jobs.monthly_summary import sync_missing_months
from jobs.scrape_bsr import _log_cron_run, _scrape_bsr
from utils.logger import get_logger
from utils.registry import BookRepo
from utils.Repo_CronRunLog import CronRunLogRepo

log = get_logger(__name__)


def _today_utc_bounds() -> tuple[str, str]:
    """Return (start, end) UTC isoformat timestamps spanning "today" in settings.TIMEZONE."""
    tz = ZoneInfo(settings.TIMEZONE)
    today_local = datetime.now(tz).date()
    start_local = datetime.combine(today_local, dt_time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc).isoformat(), end_local.astimezone(timezone.utc).isoformat()


def _asins_failed_today(cron_run_log_repo: CronRunLogRepo) -> list[str]:
    """Return ASINs whose latest scrape_bsr run today has status='failure'."""
    start_utc, end_utc = _today_utc_bounds()
    rows = cron_run_log_repo.query(
        cron_type="scrape_bsr",
        start_time=start_utc,
        end_time=end_utc,
        limit=10_000,
    )

    latest_by_asin: dict[str, tuple[str, str]] = {}
    for row in rows:
        asin = row["asin"]
        if not asin:
            continue
        if asin not in latest_by_asin or row["started_at"] > latest_by_asin[asin][1]:
            latest_by_asin[asin] = (row["status"], row["started_at"])

    return sorted(asin for asin, (status, _) in latest_by_asin.items() if status == "failure")


def retry_failed_scrapes() -> int:
    """Retry every active ASIN whose latest scrape_bsr run today failed.

    Returns the number of ASINs that are still failing after the retry.
    """
    log.info("=== retry_failed_scrapes started ===")
    cron_run_log_repo = CronRunLogRepo()
    book_repo = BookRepo()

    failed_asins = _asins_failed_today(cron_run_log_repo)
    active_asins = {str(b["asin"]) for b in book_repo.load_active_books()}
    asins_to_retry = [asin for asin in failed_asins if asin in active_asins]

    if not asins_to_retry:
        print("No failed scrape_bsr runs to retry for today.")
        return 0

    log.info("Retrying %d ASIN(s): %s", len(asins_to_retry), ", ".join(asins_to_retry))

    still_failing = 0
    for asin in asins_to_retry:
        log.info("Retrying BSR scrape for ASIN: %s", asin)
        scrape_started_at = datetime.now(timezone.utc).isoformat()
        ranks = _scrape_bsr(asin)

        if not ranks:
            still_failing += 1
            _log_cron_run(
                cron_run_log_repo,
                cron_type="scrape_bsr",
                asin=asin,
                trigger="manual",
                started_at=scrape_started_at,
                status="failure",
                detail="no BSR data found (retry)",
            )
            print(f"  {asin}: still failing")
            continue

        saved = book_repo.save_bsr_snapshots(ranks)
        _log_cron_run(
            cron_run_log_repo,
            cron_type="scrape_bsr",
            asin=asin,
            trigger="manual",
            started_at=scrape_started_at,
            status="success",
            detail=f"{len(ranks)} rank(s) saved (retry)",
        )
        print(f"  {asin}: success ({saved} snapshot(s) saved)")

        monthly_started_at = datetime.now(timezone.utc).isoformat()
        try:
            computed = sync_missing_months(asin)
            _log_cron_run(
                cron_run_log_repo,
                cron_type="monthly_summary",
                asin=asin,
                trigger="manual",
                started_at=monthly_started_at,
                status="success",
                detail=f"{computed} month(s) backfilled",
            )
        except Exception as exc:
            log.warning("ASIN %s — monthly summary sync failed (retry): %s", asin, exc)
            _log_cron_run(
                cron_run_log_repo,
                cron_type="monthly_summary",
                asin=asin,
                trigger="manual",
                started_at=monthly_started_at,
                status="failure",
                detail=str(exc),
            )

    succeeded = len(asins_to_retry) - still_failing
    print(f"\nSummary: {len(asins_to_retry)} retried — {succeeded} succeeded, {still_failing} still failing")
    log.info(
        "=== retry_failed_scrapes finished — %d/%d still failing ===",
        still_failing, len(asins_to_retry),
    )
    return still_failing


def main() -> None:
    still_failing = retry_failed_scrapes()
    sys.exit(1 if still_failing else 0)


if __name__ == "__main__":
    main()
