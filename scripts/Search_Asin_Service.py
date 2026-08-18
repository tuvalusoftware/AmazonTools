"""
Search_Asin_Service — resolves a book title to an Amazon ASIN.

Strategy
--------
1. Open the Amazon search results page via AsinPlaywrightHelper (reusing the
   saved session from ``data/browser_state.json``).
2. Collect the first 5 ``div[data-asin]`` result cards on the page.
3. Screenshot each visible card and save the images to ``data/debug/``.
4. Send all screenshots + the queried title to the configured LLM (vision
   capable) and ask it to pick the card that best matches the book.
5. Click through to the detail page, select the first format/edition in
   #tmmSwatchesList if not already selected, then extract the ASIN from
   the final page URL.
6. Return (title, asin) for the chosen card.

Raises ValueError if no ASIN candidates are found, or if the LLM determines
none of the candidates match the requested title.
Raises RuntimeError if the page could not be fetched.
"""

from __future__ import annotations

import urllib.parse
from datetime import datetime
from pathlib import Path

from config import settings
from scripts.Helper_Lookup_Asin import (
    ask_llm_asin_from_url,
    ask_llm_best_match,
)
from scripts.AsinPlaywright_Helper import AsinPlaywrightHelper
from utils.logger import get_logger

log = get_logger(__name__)

_SEARCH_URL = "https://www.amazon.com/s?k={query}&i=stripbooks"


class SearchAsinService:
    """Resolve a book title to an Amazon ASIN using Playwright + LLM vision."""

    def __init__(self, title: str) -> None:
        self.title = title
        self._debug_dir = Path(settings.OUTPUT_DIR) / "debug"

    def search(self) -> tuple[str, str]:
        """Run the ASIN lookup and return ``(title, asin)``.

        Raises
        ------
        ValueError
            If no ASIN candidates are found on the results page, or if the LLM
            determines that none of the candidates match the requested title.
        RuntimeError
            If the page could not be fetched.
        """
        query = urllib.parse.quote_plus(self.title)
        url = _SEARCH_URL.format(query=query)
        self._debug_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        helper = AsinPlaywrightHelper()
        try:
            helper.open_page(url)

            helper.collect_candidates()
            if not helper.asins:
                raise ValueError(f"ASIN not found for title: {self.title!r}")

            screenshots = helper.screenshot_candidates(timestamp, self._debug_dir)
            best_idx, detail_asin = self._pick_best_asin(helper, screenshots, timestamp)
            helper.save_state()
        finally:
            helper.close()

        return self._build_return_tuple(helper.asins, screenshots, best_idx, detail_asin)

    # ---------------------------------------------------------------------- #
    # Private helpers                                                          #
    # ---------------------------------------------------------------------- #

    def _pick_best_asin(
        self,
        helper: AsinPlaywrightHelper,
        screenshots: list[Path],
        timestamp: str,
    ) -> tuple[int, str | None]:
        """Ask the LLM to choose the best card, then extract the ASIN from its
        detail page.  Returns (best_idx, detail_asin)."""
        best_idx = -1
        if screenshots:
            log.info(
                "lookup_asin: sending %d screenshot(s) to LLM for best-match evaluation …",
                len(screenshots),
            )
            best_idx = ask_llm_best_match(self.title, screenshots)

        for p in screenshots:
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass

        detail_asin: str | None = None
        if best_idx >= 0:
            if best_idx >= len(helper.asins):
                best_idx = 0
            detail_url = helper.navigate_to_detail(
                helper.el_indices[best_idx],
                helper.asins[best_idx],
                self._debug_dir,
                timestamp,
            )
            if detail_url:
                detail_asin = ask_llm_asin_from_url(detail_url) or None

        return best_idx, detail_asin

    def _build_return_tuple(
        self,
        asins: list[str],
        screenshots: list[Path],
        best_idx: int,
        detail_asin: str | None,
    ) -> tuple[str, str]:
        """Turn the raw lookup outputs into a final (title, asin) pair."""
        if not screenshots:
            log.warning(
                "lookup_asin: no screenshots captured — using first candidate ASIN %s",
                asins[0],
            )
            return self.title, asins[0]

        if best_idx == -1:
            raise ValueError(
                f"ASIN not found for title: {self.title!r} "
                f"(LLM evaluated {len(screenshots)} candidate(s) and found no match)"
            )

        search_asin = asins[best_idx]
        log.info(
            "lookup_asin: LLM chose card %d → search ASIN %s  (%d candidate(s) total)",
            best_idx + 1, search_asin, len(asins),
        )

        if detail_asin:
            log.info(
                "lookup_asin: detail-page ASIN (first edition) → %s%s",
                detail_asin,
                f"  (differs from search card: {search_asin})" if detail_asin != search_asin else "",
            )
            return self.title, detail_asin

        log.warning(
            "lookup_asin: could not extract ASIN from detail page — falling back to search card ASIN %s",
            search_asin,
        )
        return self.title, search_asin
