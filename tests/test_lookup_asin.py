"""Unit tests for scripts/lookup_asin.py — search_asin function."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from scripts.lookup_asin import search_asin


def _html_with_asins(*asins: str) -> str:
    """Return minimal Amazon-like HTML containing one div[data-asin] per ASIN."""
    divs = "\n".join(
        f'<div data-asin="{asin}"><span>Some Book</span></div>' for asin in asins
    )
    return f"<html><body>{divs}</body></html>"


class TestSearchAsin:
    def test_search_asin_returns_title_and_asin(self) -> None:
        html = _html_with_asins("0735211299")
        with patch("scripts.lookup_asin.fetch_page_html", return_value=html):
            title, asin = search_asin("Atomic Habits")
        assert title == "Atomic Habits"
        assert asin == "0735211299"

    def test_search_asin_uses_first_candidate(self) -> None:
        html = _html_with_asins("FIRST1234", "SECOND123", "THIRD1234")
        with patch("scripts.lookup_asin.fetch_page_html", return_value=html):
            _, asin = search_asin("Some Book")
        assert asin == "FIRST1234"

    def test_search_asin_raises_value_error_when_no_asin(self) -> None:
        html = "<html><body><div>No data-asin here</div></body></html>"
        with patch("scripts.lookup_asin.fetch_page_html", return_value=html):
            with pytest.raises(ValueError, match="ASIN not found"):
                search_asin("Ghost Book")

    def test_search_asin_ignores_empty_data_asin(self) -> None:
        html = (
            '<html><body>'
            '<div data-asin=""></div>'
            '<div data-asin="   "></div>'
            '<div data-asin="REAL1234"></div>'
            '</body></html>'
        )
        with patch("scripts.lookup_asin.fetch_page_html", return_value=html):
            _, asin = search_asin("Some Book")
        assert asin == "REAL1234"
