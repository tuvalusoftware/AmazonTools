"""Unit tests for scripts/Search_Asin_Service.py — SearchAsinService.search."""

from __future__ import annotations

import contextlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.Search_Asin_Service import SearchAsinService


def _make_service(title: str = "Atomic Habits") -> SearchAsinService:
    return SearchAsinService(title)


@contextlib.contextmanager
def _browser_stub(
    svc: SearchAsinService,
    *,
    asins: list[str],
    screenshots: list[Path],
    best_idx: int,
    detail_asin: str | None,
):
    """Patch AsinPlaywrightHelper and _pick_best_asin so search() never opens a real browser."""
    helper_mock = MagicMock()
    helper_mock.asins = asins
    helper_mock.el_indices = list(range(len(asins)))
    helper_mock.screenshot_candidates.return_value = screenshots

    with (
        patch("scripts.Search_Asin_Service.AsinPlaywrightHelper", return_value=helper_mock),
        patch.object(svc, "_pick_best_asin", return_value=(best_idx, detail_asin)),
    ):
        yield


class TestSearchAsinService:
    def test_search_returns_title_and_asin(self) -> None:
        svc = _make_service("Atomic Habits")
        with _browser_stub(svc, asins=["0735211299"], screenshots=[Path("fake.png")], best_idx=0, detail_asin=None):
            title, asin = svc.search()
        assert title == "Atomic Habits"
        assert asin == "0735211299"

    def test_search_uses_first_candidate_when_no_screenshots(self) -> None:
        svc = _make_service("Some Book")
        with _browser_stub(svc, asins=["FIRST1234", "SECOND123"], screenshots=[], best_idx=-1, detail_asin=None):
            _, asin = svc.search()
        assert asin == "FIRST1234"

    def test_search_raises_value_error_when_no_asin(self) -> None:
        svc = _make_service("Ghost Book")
        with _browser_stub(svc, asins=[], screenshots=[], best_idx=-1, detail_asin=None):
            with pytest.raises(ValueError, match="ASIN not found"):
                svc.search()

    def test_search_raises_value_error_when_llm_finds_no_match(self) -> None:
        svc = _make_service("Ghost Book")
        with _browser_stub(svc, asins=["ASIN000001"], screenshots=[Path("fake.png")], best_idx=-1, detail_asin=None):
            with pytest.raises(ValueError, match="ASIN not found"):
                svc.search()

    def test_search_prefers_detail_asin_over_search_card(self) -> None:
        svc = _make_service("Some Book")
        with _browser_stub(svc, asins=["SEARCH1234"], screenshots=[Path("fake.png")], best_idx=0, detail_asin="DETAIL1234"):
            _, asin = svc.search()
        assert asin == "DETAIL1234"

    def test_search_falls_back_to_search_card_when_detail_missing(self) -> None:
        svc = _make_service("Some Book")
        with _browser_stub(svc, asins=["SEARCH1234"], screenshots=[Path("fake.png")], best_idx=0, detail_asin=None):
            _, asin = svc.search()
        assert asin == "SEARCH1234"
