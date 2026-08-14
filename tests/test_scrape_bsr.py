"""Unit tests for jobs/scrape_bsr.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from jobs.scrape_bsr import BestSellerRank, _parse_price, run
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# BestSellerRank dataclass
# ---------------------------------------------------------------------------


def test_bestsellerrank_price_field_defaults_to_zero() -> None:
    bsr = BestSellerRank(asin="X", rank=1, category="cat", scraped_at="now")
    assert bsr.price == 0.0


# ---------------------------------------------------------------------------
# _parse_price — selector coverage
# ---------------------------------------------------------------------------


def test_price_scraped_from_first_selector() -> None:
    html = '<html><body><span class="a-offscreen">$14.99</span></body></html>'
    soup = BeautifulSoup(html, "html.parser")
    assert _parse_price(soup) == 14.99


def test_price_falls_back_through_selectors() -> None:
    html = '<html><body><span id="kindle-price">$9.99</span></body></html>'
    soup = BeautifulSoup(html, "html.parser")
    assert _parse_price(soup) == 9.99


def test_price_defaults_to_zero_when_no_selector_matches() -> None:
    html = "<html><body><p>No price here</p></body></html>"
    soup = BeautifulSoup(html, "html.parser")
    assert _parse_price(soup) == 0.0


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
    ):
        run()

    mock_scrape.assert_called_once_with("B00TEST123")
