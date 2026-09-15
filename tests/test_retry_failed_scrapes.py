"""Unit tests for scripts/retry_failed_scrapes.py."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from jobs.scrape_bsr import BestSellerRank
from scripts.retry_failed_scrapes import retry_failed_scrapes


def _row(asin: str, status: str, started_at: str, cron_type: str = "scrape_bsr") -> dict:
    return {
        "id": 1,
        "cron_type": cron_type,
        "asin": asin,
        "trigger": "cron",
        "started_at": started_at,
        "finished_at": started_at,
        "status": status,
        "detail": None,
    }


def _active_book(asin: str) -> dict:
    return {"asin": asin, "email": "a@example.com", "title": "T", "profit_pct": 0.7, "current_price": 9.99, "active": 1}


def _today_iso(hour: int = 10) -> str:
    return datetime.now(timezone.utc).replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


def _yesterday_iso(hour: int = 10) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=1)).replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


def test_asin_failed_today_is_retried() -> None:
    mock_cron_log = MagicMock()
    mock_cron_log.query.return_value = [_row("B001", "failure", _today_iso())]
    mock_book_repo = MagicMock()
    mock_book_repo.load_active_books.return_value = [_active_book("B001")]
    mock_book_repo.save_bsr_snapshots.return_value = 1

    fake_rank = BestSellerRank(asin="B001", rank=1, category="Books")

    with (
        patch("scripts.retry_failed_scrapes.CronRunLogRepo", return_value=mock_cron_log),
        patch("scripts.retry_failed_scrapes.BookRepo", return_value=mock_book_repo),
        patch("scripts.retry_failed_scrapes._scrape_bsr", return_value=[fake_rank]) as mock_scrape,
        patch("scripts.retry_failed_scrapes.sync_missing_months", return_value=0),
    ):
        still_failing = retry_failed_scrapes()

    mock_scrape.assert_called_once_with("B001")
    assert still_failing == 0


def test_asin_failed_then_succeeded_later_today_is_skipped() -> None:
    mock_cron_log = MagicMock()
    mock_cron_log.query.return_value = [
        _row("B001", "success", _today_iso(hour=12)),
        _row("B001", "failure", _today_iso(hour=9)),
    ]
    mock_book_repo = MagicMock()
    mock_book_repo.load_active_books.return_value = [_active_book("B001")]

    with (
        patch("scripts.retry_failed_scrapes.CronRunLogRepo", return_value=mock_cron_log),
        patch("scripts.retry_failed_scrapes.BookRepo", return_value=mock_book_repo),
        patch("scripts.retry_failed_scrapes._scrape_bsr") as mock_scrape,
        patch("scripts.retry_failed_scrapes.sync_missing_months"),
    ):
        still_failing = retry_failed_scrapes()

    mock_scrape.assert_not_called()
    assert still_failing == 0


def test_yesterdays_failure_is_skipped(tmp_db) -> None:
    """Uses the real CronRunLogRepo/BookRepo against a temp SQLite DB so the
    today-boundary math in _asins_failed_today runs for real, not mocked."""
    from utils.Repo_CronRunLog import CronRunLogRepo

    tmp_db.register_book(
        {"email": "a@example.com", "title": "T", "asin": "B001", "profit_pct": 0.7, "current_price": 9.99}
    )
    cron_log = CronRunLogRepo(db_path=tmp_db._db_path)
    cron_log.save(
        "scrape_bsr",
        asin="B001",
        trigger="cron",
        started_at=_yesterday_iso(),
        finished_at=_yesterday_iso(),
        status="failure",
        detail="no BSR data found",
    )

    with (
        patch("scripts.retry_failed_scrapes.CronRunLogRepo", return_value=cron_log),
        patch("scripts.retry_failed_scrapes.BookRepo", return_value=tmp_db),
        patch("scripts.retry_failed_scrapes._scrape_bsr") as mock_scrape,
        patch("scripts.retry_failed_scrapes.sync_missing_months"),
    ):
        still_failing = retry_failed_scrapes()

    mock_scrape.assert_not_called()
    assert still_failing == 0


def test_inactive_asin_is_skipped() -> None:
    mock_cron_log = MagicMock()
    mock_cron_log.query.return_value = [_row("B001", "failure", _today_iso())]
    mock_book_repo = MagicMock()
    mock_book_repo.load_active_books.return_value = []  # B001 not active

    with (
        patch("scripts.retry_failed_scrapes.CronRunLogRepo", return_value=mock_cron_log),
        patch("scripts.retry_failed_scrapes.BookRepo", return_value=mock_book_repo),
        patch("scripts.retry_failed_scrapes._scrape_bsr") as mock_scrape,
        patch("scripts.retry_failed_scrapes.sync_missing_months"),
    ):
        still_failing = retry_failed_scrapes()

    mock_scrape.assert_not_called()
    assert still_failing == 0


def test_nothing_to_retry_returns_zero() -> None:
    mock_cron_log = MagicMock()
    mock_cron_log.query.return_value = []
    mock_book_repo = MagicMock()
    mock_book_repo.load_active_books.return_value = [_active_book("B001")]

    with (
        patch("scripts.retry_failed_scrapes.CronRunLogRepo", return_value=mock_cron_log),
        patch("scripts.retry_failed_scrapes.BookRepo", return_value=mock_book_repo),
    ):
        assert retry_failed_scrapes() == 0


def test_still_failing_after_retry_is_counted() -> None:
    mock_cron_log = MagicMock()
    mock_cron_log.query.return_value = [_row("B001", "failure", _today_iso())]
    mock_book_repo = MagicMock()
    mock_book_repo.load_active_books.return_value = [_active_book("B001")]

    with (
        patch("scripts.retry_failed_scrapes.CronRunLogRepo", return_value=mock_cron_log),
        patch("scripts.retry_failed_scrapes.BookRepo", return_value=mock_book_repo),
        patch("scripts.retry_failed_scrapes._scrape_bsr", return_value=[]),
        patch("scripts.retry_failed_scrapes.sync_missing_months") as mock_sync,
    ):
        still_failing = retry_failed_scrapes()

    mock_sync.assert_not_called()
    assert still_failing == 1
