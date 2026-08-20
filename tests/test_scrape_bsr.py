"""Unit tests for jobs/scrape_bsr.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from jobs.scrape_bsr import BestSellerRank, run
from utils.browser import extract_price_from_html


# ---------------------------------------------------------------------------
# BestSellerRank dataclass
# ---------------------------------------------------------------------------


def test_bestsellerrank_price_field_defaults_to_zero() -> None:
    bsr = BestSellerRank(asin="X", rank=1, category="cat", scraped_at="now")
    assert bsr.price == 0.0


# ---------------------------------------------------------------------------
# extract_price_from_html — selector coverage
# ---------------------------------------------------------------------------


def test_price_scraped_from_data_pricetopay_label() -> None:
    html = '<html><body><span data-pricetopay-label aria-label="$14.99 with 50 percent savings"></span></body></html>'
    assert extract_price_from_html(html) == 14.99


def test_price_falls_back_through_selectors() -> None:
    html = '<html><body><span id="kindle-price">$9.99</span></body></html>'
    assert extract_price_from_html(html) == 9.99


def test_price_falls_back_to_a_price_text() -> None:
    html = (
        '<html><body><span class="a-price">'
        '<span class="a-price-whole">12.</span>'
        '<span class="a-price-fraction">34</span>'
        "</span></body></html>"
    )
    assert extract_price_from_html(html) == 12.34


def test_price_defaults_to_zero_when_no_selector_matches() -> None:
    html = "<html><body><p>No price here</p></body></html>"
    assert extract_price_from_html(html) == 0.0


# ---------------------------------------------------------------------------
# run() — BookRepo interaction
# ---------------------------------------------------------------------------


def test_run_skips_when_no_active_books(caplog: pytest.LogCaptureFixture) -> None:
    mock_repo = MagicMock()
    mock_repo.load_active_books.return_value = []

    with patch("jobs.scrape_bsr.BookRepo", return_value=mock_repo):
        import logging
        with caplog.at_level(logging.INFO, logger="jobs.scrape_bsr"):
            run()

    mock_repo.save_bsr_snapshots.assert_not_called()
    assert any("No active ASINs" in r.message for r in caplog.records)


def test_run_queries_active_books_from_registry() -> None:
    mock_repo = MagicMock()
    mock_repo.load_active_books.return_value = [
        {
            "asin": "B00TEST123",
            "email": "author@example.com",
            "title": "Test Book",
            "profit_pct": 0.70,
            "current_price": 9.99,
            "active": 1,
        }
    ]
    mock_repo.save_bsr_snapshots.return_value = 1

    fake_rank = BestSellerRank(asin="B00TEST123", rank=42, category="Books > Test")

    with (
        patch("jobs.scrape_bsr.BookRepo", return_value=mock_repo),
        patch("jobs.scrape_bsr._scrape_bsr", return_value=[fake_rank]) as mock_scrape,
        patch("jobs.scrape_bsr.sync_missing_months") as mock_sync,
        patch("jobs.scrape_bsr.CronRunLogRepo"),
    ):
        run()

    mock_scrape.assert_called_once_with("B00TEST123")
    mock_sync.assert_called_once_with("B00TEST123")


# ---------------------------------------------------------------------------
# run() — cron_run_log writes
# ---------------------------------------------------------------------------


def test_run_logs_success_row_for_scrape_and_monthly_summary() -> None:
    mock_repo = MagicMock()
    mock_repo.load_active_books.return_value = [_active_book("B00TEST123")]
    mock_repo.save_bsr_snapshots.return_value = 1

    fake_rank = BestSellerRank(asin="B00TEST123", rank=42, category="Books > Test")
    mock_cron_log = MagicMock()

    with (
        patch("jobs.scrape_bsr.BookRepo", return_value=mock_repo),
        patch("jobs.scrape_bsr._scrape_bsr", return_value=[fake_rank]),
        patch("jobs.scrape_bsr.sync_missing_months", return_value=2),
        patch("jobs.scrape_bsr.CronRunLogRepo", return_value=mock_cron_log),
    ):
        run()

    assert mock_cron_log.save.call_count == 2
    cron_types = {c.kwargs.get("trigger") for c in mock_cron_log.save.call_args_list}
    assert "cron" in cron_types
    assert "scrape_bsr" in cron_types
    statuses = {c.args[0]: c.kwargs["status"] for c in mock_cron_log.save.call_args_list}
    assert statuses == {"scrape_bsr": "success", "monthly_summary": "success"}


def test_run_logs_failure_row_when_no_ranks_found_and_no_monthly_summary_row() -> None:
    mock_repo = MagicMock()
    mock_repo.load_active_books.return_value = [_active_book("B00TEST123")]
    mock_cron_log = MagicMock()

    with (
        patch("jobs.scrape_bsr.BookRepo", return_value=mock_repo),
        patch("jobs.scrape_bsr._scrape_bsr", return_value=[]),
        patch("jobs.scrape_bsr.sync_missing_months") as mock_sync,
        patch("jobs.scrape_bsr.CronRunLogRepo", return_value=mock_cron_log),
    ):
        run()

    mock_sync.assert_not_called()
    assert mock_cron_log.save.call_count == 1
    call = mock_cron_log.save.call_args
    assert call.args[0] == "scrape_bsr"
    assert call.kwargs["status"] == "failure"


def test_run_logs_failure_row_when_sync_missing_months_raises() -> None:
    mock_repo = MagicMock()
    mock_repo.load_active_books.return_value = [_active_book("B00TEST123")]
    mock_repo.save_bsr_snapshots.return_value = 1
    fake_rank = BestSellerRank(asin="B00TEST123", rank=42, category="Books > Test")
    mock_cron_log = MagicMock()

    with (
        patch("jobs.scrape_bsr.BookRepo", return_value=mock_repo),
        patch("jobs.scrape_bsr._scrape_bsr", return_value=[fake_rank]),
        patch("jobs.scrape_bsr.sync_missing_months", side_effect=RuntimeError("boom")),
        patch("jobs.scrape_bsr.CronRunLogRepo", return_value=mock_cron_log),
    ):
        run()

    calls_by_type = {c.args[0]: c.kwargs["status"] for c in mock_cron_log.save.call_args_list}
    assert calls_by_type["monthly_summary"] == "failure"


def test_run_cron_run_log_save_raising_does_not_abort_job() -> None:
    mock_repo = MagicMock()
    mock_repo.load_active_books.return_value = [_active_book("B00TEST123")]
    mock_repo.save_bsr_snapshots.return_value = 1
    fake_rank = BestSellerRank(asin="B00TEST123", rank=42, category="Books > Test")
    mock_cron_log = MagicMock()
    mock_cron_log.save.side_effect = RuntimeError("db down")

    with (
        patch("jobs.scrape_bsr.BookRepo", return_value=mock_repo),
        patch("jobs.scrape_bsr._scrape_bsr", return_value=[fake_rank]),
        patch("jobs.scrape_bsr.sync_missing_months", return_value=0),
        patch("jobs.scrape_bsr.CronRunLogRepo", return_value=mock_cron_log),
    ):
        run()  # must not raise

    mock_repo.save_bsr_snapshots.assert_called_once()


# ---------------------------------------------------------------------------
# run() — monthly summary self-heal trigger
# ---------------------------------------------------------------------------


def _active_book(asin: str = "B00TEST123") -> dict:
    return {
        "asin": asin,
        "email": "author@example.com",
        "title": "Test Book",
        "profit_pct": 0.70,
        "current_price": 9.99,
        "active": 1,
    }


def test_run_sync_missing_months_failure_does_not_abort_loop() -> None:
    mock_repo = MagicMock()
    mock_repo.load_active_books.return_value = [_active_book("B00TEST123"), _active_book("B00TEST456")]
    mock_repo.save_bsr_snapshots.return_value = 1

    fake_rank_a = BestSellerRank(asin="B00TEST123", rank=42, category="Books > Test")
    fake_rank_b = BestSellerRank(asin="B00TEST456", rank=99, category="Books > Test")

    with (
        patch("jobs.scrape_bsr.BookRepo", return_value=mock_repo),
        patch("jobs.scrape_bsr._scrape_bsr", side_effect=[[fake_rank_a], [fake_rank_b]]),
        patch("jobs.scrape_bsr.sync_missing_months", side_effect=[RuntimeError("boom"), 0]) as mock_sync,
        patch("jobs.scrape_bsr.CronRunLogRepo"),
    ):
        run()

    assert mock_sync.call_count == 2
    assert mock_repo.save_bsr_snapshots.call_count == 2


def test_run_does_not_sync_missing_months_when_no_ranks() -> None:
    mock_repo = MagicMock()
    mock_repo.load_active_books.return_value = [_active_book("B00TEST123")]

    with (
        patch("jobs.scrape_bsr.BookRepo", return_value=mock_repo),
        patch("jobs.scrape_bsr._scrape_bsr", return_value=[]),
        patch("jobs.scrape_bsr.sync_missing_months") as mock_sync,
        patch("jobs.scrape_bsr.CronRunLogRepo"),
    ):
        run()

    mock_sync.assert_not_called()
    mock_repo.save_bsr_snapshots.assert_not_called()
