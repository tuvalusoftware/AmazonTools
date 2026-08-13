"""
ASIN lookup helper.

Public API
----------
search_asin(title: str) -> tuple[str, str]
    Resolves a book title to an Amazon ASIN using a Playwright-rendered
    search results page.  Returns (title, asin).  Raises ValueError if
    no ASIN is found.
"""

from __future__ import annotations

import urllib.parse

from bs4 import BeautifulSoup

from utils.browser import fetch_page_html
from utils.logger import get_logger

log = get_logger(__name__)

_SEARCH_URL = "https://www.amazon.com/s?k={query}&i=stripbooks"


def search_asin(title: str) -> tuple[str, str]:
    """
    Search Amazon for *title* and return (title, asin) using the first
    search result.

    Raises
    ------
    ValueError
        If no ASIN candidates are found on the results page.
    RuntimeError
        If the page could not be fetched.
    """
    query = urllib.parse.quote_plus(title)
    url = _SEARCH_URL.format(query=query)

    html = fetch_page_html(url)
    if not html:
        raise RuntimeError(f"Failed to fetch search results page for title: {title!r}")

    soup = BeautifulSoup(html, "html.parser")
    candidates: list[str] = [
        str(div["data-asin"])
        for div in soup.find_all("div", attrs={"data-asin": True})
        if str(div["data-asin"]).strip()
    ]

    if not candidates:
        raise ValueError(f"ASIN not found for title: {title!r}")

    asin = candidates[0]
    log.info(
        "search_asin: resolved %r → %s  (%d candidate(s) found)",
        title,
        asin,
        len(candidates),
    )
    return title, asin
