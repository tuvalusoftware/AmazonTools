"""
AsinPlaywright_Helper — low-level browser automation helpers.

Encapsulates every direct Playwright interaction used by the ASIN-lookup
pipeline so that callers (SearchAsinService, extract_asin_from_detail_page)
never touch the Playwright API themselves.

Responsibilities
----------------
- Launch a Chromium browser with an optional persisted storage state.
- Navigate to a URL and collect candidate cards (state stored internally).
- Screenshot individual result cards.
- Click through to a book's detail page, interact with #tmmSwatchesList, and
  return the final page URL.
- Persist the browser storage state back to disk after a session.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from playwright.sync_api import BrowserContext, Locator, Page, sync_playwright
from config import settings
from scripts.Helper_Lookup_Asin import ask_llm_first_item_selected
from utils.logger import get_logger

log = get_logger(__name__)

_MAX_CANDIDATES = 5
_DETAIL_SWATCH_SELECTOR = "#tmmSwatchesList"


class AsinPlaywrightHelper:
    """Browser-automation helper for the ASIN-lookup pipeline.

    Typical usage::

        helper = AsinPlaywrightHelper()
        helper.open_page(url)
        helper.collect_candidates()
        screenshots = helper.screenshot_candidates(timestamp, debug_dir)
        url = helper.navigate_to_detail(el_idx, asin, debug_dir, timestamp, ask_first_selected_fn)
        helper.save_state()
        helper.close()

    After :meth:`open_page` the active page is available as :attr:`page`.
    After :meth:`collect_candidates` the results are available as :attr:`asins`
    and :attr:`el_indices`.

    Parameters
    ----------
    state_path:
        Path to the Playwright storage-state JSON file.  When the file
        exists it is loaded into the browser context so the logged-in session
        is reused.
    """

    def __init__(self, state_path: Path | None = None) -> None:
        self._state_path: Path = state_path or Path(settings.BROWSER_STATE_PATH)
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=settings.BROWSER_HEADLESS)
        self._context: BrowserContext = self._make_context()
        self._page: Page | None = None
        self._all_asin_els: Locator | None = None
        self.asins: list[str] = []
        self.el_indices: list[int] = []

    # ---------------------------------------------------------------------- #
    # Context / lifecycle                                                      #
    # ---------------------------------------------------------------------- #

    def _make_context(self) -> BrowserContext:
        ctx_opts: dict[str, Any] = {}
        if self._state_path.exists():
            ctx_opts["storage_state"] = str(self._state_path)
        return self._browser.new_context(**ctx_opts)

    def save_state(self) -> None:
        """Persist the current browser context's storage state to disk."""
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            self._context.storage_state(path=str(self._state_path))
        except Exception as exc:
            log.warning("AsinPlaywrightHelper: could not save browser state — %s", exc)

    def close(self) -> None:
        """Close the browser and stop the Playwright process."""
        try:
            self._browser.close()
        finally:
            self._pw.stop()

    # ---------------------------------------------------------------------- #
    # Navigation                                                               #
    # ---------------------------------------------------------------------- #

    def open_page(self, url: str) -> None:
        """Navigate a new page to *url* and store it as :attr:`_page`.

        Raises
        ------
        RuntimeError
            If the page fails to load.
        """
        page = self._context.new_page()
        try:
            page.goto(url, wait_until="load", timeout=30_000)
        except Exception as exc:
            raise RuntimeError(f"AsinPlaywrightHelper: page load error — {exc}") from exc
        self._page = page

    # ---------------------------------------------------------------------- #
    # Candidate collection                                                     #
    # ---------------------------------------------------------------------- #

    def collect_candidates(
        self,
        max_candidates: int = _MAX_CANDIDATES,
    ) -> None:
        """Scan the current page for ``div[data-asin]`` elements and store the
        first *max_candidates* unique ASIN values together with their DOM
        indices in :attr:`asins` and :attr:`el_indices`.

        Raises
        ------
        RuntimeError
            If :meth:`open_page` has not been called first.
        """
        if self._page is None:
            raise RuntimeError("AsinPlaywrightHelper: call open_page() before collect_candidates()")
        all_asin_els = self._page.locator("div[data-asin]")
        count = all_asin_els.count()
        asins: list[str] = []
        el_indices: list[int] = []
        seen: set[str] = set()
        for i in range(count):
            if len(el_indices) >= max_candidates:
                break
            try:
                val = (all_asin_els.nth(i).get_attribute("data-asin") or "").strip()
                if val and val not in seen:
                    seen.add(val)
                    asins.append(val)
                    el_indices.append(i)
            except Exception:
                continue
        self._all_asin_els = all_asin_els
        self.asins = asins
        self.el_indices = el_indices

    # ---------------------------------------------------------------------- #
    # Screenshot helpers                                                       #
    # ---------------------------------------------------------------------- #

    def screenshot_candidates(
        self,
        timestamp: str,
        debug_dir: Path,
    ) -> list[Path]:
        """Screenshot each visible candidate card and return the saved paths.

        Parameters
        ----------
        timestamp:
            String timestamp appended to each filename (``YYYYMMDD_HHMMSS``).
        debug_dir:
            Directory where screenshot PNGs are written.

        Raises
        ------
        RuntimeError
            If :meth:`collect_candidates` has not been called first.
        """
        if self._all_asin_els is None:
            raise RuntimeError(
                "AsinPlaywrightHelper: call collect_candidates() before screenshot_candidates()"
            )
        log.info(
            "AsinPlaywrightHelper: found %d candidate ASIN(s) — screenshotting each …",
            len(self.asins),
        )
        paths: list[Path] = []
        for rank, (asin, el_idx) in enumerate(zip(self.asins, self.el_indices)):
            try:
                el = self._all_asin_els.nth(el_idx)
                if not el.is_visible(timeout=3_000):
                    log.debug(
                        "AsinPlaywrightHelper: candidate %d (ASIN %s) not visible — skipping",
                        rank + 1, asin,
                    )
                    continue
                path = debug_dir / f"lookup_asin_{rank + 1}_{timestamp}.png"
                el.screenshot(path=str(path))
                paths.append(path)
                log.info(
                    "AsinPlaywrightHelper: screenshot %d/%d saved → %s",
                    rank + 1, len(self.asins), path,
                )
            except Exception as exc:
                log.debug(
                    "AsinPlaywrightHelper: screenshot failed for candidate %d: %s",
                    rank + 1, exc,
                )
        return paths

    # ---------------------------------------------------------------------- #
    # Detail-page navigation                                                   #
    # ---------------------------------------------------------------------- #

    def navigate_to_detail(
        self,
        el_idx: int,
        asin: str,
        debug_dir: Path,
        timestamp: str,
    ) -> str | None:
        """Click through to the detail page for the chosen result card,
        interact with ``#tmmSwatchesList``, and return the final page URL.

        The caller is responsible for ASIN extraction from the URL.

        Parameters
        ----------
        el_idx:
            DOM index of the chosen card (from :attr:`el_indices`).
        asin:
            ASIN string of the chosen card (used for logging only).
        debug_dir:
            Directory where the swatch screenshot is temporarily saved.
        timestamp:
            Timestamp string appended to temporary filenames.

        Returns
        -------
        str | None
            The URL of the final detail page after swatch interaction, or
            ``None`` if any step fails.

        Raises
        ------
        RuntimeError
            If :meth:`open_page` has not been called first.
        """
        if self._page is None or self._all_asin_els is None:
            raise RuntimeError(
                "AsinPlaywrightHelper: call open_page() and collect_candidates() first"
            )
        page = self._page
        all_asin_els = self._all_asin_els
        try:
            el = all_asin_els.nth(el_idx)
            link = el.locator("a.a-link-normal").first
            if not link.is_visible(timeout=3_000):
                log.debug("AsinPlaywrightHelper: detail link not visible for ASIN %s", asin)
                return None

            log.info("AsinPlaywrightHelper: clicking through to detail page for ASIN %s …", asin)
            link.click()
            # "load" is sufficient — Amazon detail pages continuously fire background
            # requests so "networkidle" never completes within a reasonable timeout.
            page.wait_for_load_state("load", timeout=30_000)

            swatch = page.locator(_DETAIL_SWATCH_SELECTOR)
            if not swatch.is_visible(timeout=5_000):
                log.warning(
                    "AsinPlaywrightHelper: #tmmSwatchesList not visible for ASIN %s — "
                    "using current URL as-is",
                    asin,
                )
            else:
                swatch_path = debug_dir / f"lookup_asin_swatch_{asin}_{timestamp}.png"
                swatch.screenshot(path=str(swatch_path))

                first_selected = ask_llm_first_item_selected(swatch_path)

                try:
                    swatch_path.unlink(missing_ok=True)
                except Exception:
                    pass

                log.info(
                    "AsinPlaywrightHelper: LLM says first swatch item is %s selected",
                    "already" if first_selected else "NOT yet",
                )

                if not first_selected:
                    first_link = swatch.locator("a").first
                    if first_link.is_visible(timeout=3_000):
                        log.info(
                            "AsinPlaywrightHelper: clicking first swatch item for ASIN %s …", asin,
                        )
                        first_link.click()
                        page.wait_for_load_state("load", timeout=30_000)
                    else:
                        log.warning(
                            "AsinPlaywrightHelper: first swatch <a> not visible for ASIN %s", asin,
                        )

            current_url = page.url
            log.info("AsinPlaywrightHelper: final detail URL → %s", current_url)

            page.go_back(wait_until="load", timeout=20_000)
            return current_url

        except Exception as exc:
            log.warning(
                "AsinPlaywrightHelper: could not navigate to detail page for ASIN %s: %s",
                asin, exc,
            )
            return None
