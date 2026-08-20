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
    ):
        run()

    mock_scrape.assert_called_once_with("B00TEST123")
