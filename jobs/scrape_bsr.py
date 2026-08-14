"""
Job: scrape Amazon Best Seller Rank (BSR) for each target ASIN.

Flow per ASIN:
  1. utils.browser.fetch_page_html() fetches the fully-rendered product page.
  2. The HTML is passed to SmartScraperGraph so the LLM extracts BSR data.
  3. Price is parsed inline from the same HTML (no extra HTTP request).
  4. Results are persisted to the bsr_snapshots SQLite table via BookRepo.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from scrapegraphai.graphs import SmartScraperGraph

from config import settings, build_graph_config
from utils.browser import fetch_page_html
from utils.logger import get_logger
from utils.registry import BookRepo

log = get_logger(__name__)


@dataclass
class BestSellerRank:
    asin: str
    rank: int
    category: str
    price: float = 0.0
    scraped_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


_PROMPT = """
Extract ALL Best Sellers Rank entries visible on this Amazon product page.
Return a JSON object with a single key "ranks" containing an array.
Each element must have:
  - rank     : the integer rank number (e.g. 1523)
  - category : the full category path string exactly as shown (e.g. "Books > Science")
"""

_PRICE_SELECTORS = [
    "span.a-offscreen",
    "span#price_inside_buybox",
    "span#kindle-price",
    "span.a-color-price",
]


def _parse_price(soup: BeautifulSoup) -> float:
    """Extract price from an already-parsed Amazon product page soup.

    Tries selectors in priority order; strips currency symbols and whitespace
    before casting to float.  Returns 0.0 if nothing parseable is found.
    """
    for selector in _PRICE_SELECTORS:
        tag = soup.select_one(selector)
        if not tag:
            continue
        cleaned = re.sub(r"[^\d.]", "", tag.get_text(strip=True))
        try:
            value = float(cleaned)
        except ValueError:
            continue
        if value > 0:
            return value
    return 0.0


def _scrape_bsr(
    asin: str,
    *,
    retries: int | None = None,
    retry_delay: float | None = None,
) -> list[BestSellerRank]:
    """Fetch and parse BSR entries for *asin*.

    Retries up to *retries* extra times (default: ``settings.SCRAPE_RETRIES``)
    when the page loads but the LLM returns no ranks — which typically means
    Amazon served a CAPTCHA or an interstitial page.  Each retry waits
    *retry_delay* seconds (default: ``settings.SCRAPE_RETRY_DELAY``) with a
    small exponential factor so successive attempts space out more.
    """
    max_retries = retries if retries is not None else settings.SCRAPE_RETRIES
    base_delay = retry_delay if retry_delay is not None else settings.SCRAPE_RETRY_DELAY
    url = settings.AMAZON_PRODUCT_URL.format(asin=asin)

    for attempt in range(1 + max_retries):
        if attempt > 0:
            wait = base_delay * (2 ** (attempt - 1))
            log.info(
                "scrape_bsr: ASIN %s retry %d/%d — waiting %.0fs …",
                asin, attempt, max_retries, wait,
            )
            time.sleep(wait)

        log.debug("Fetching ASIN %s (attempt %d): %s", asin, attempt + 1, url)

        html = fetch_page_html(url)
        if not html:
            log.warning("scrape_bsr: ASIN %s — could not fetch HTML (attempt %d)", asin, attempt + 1)
            continue

        soup = BeautifulSoup(html, "html.parser")
        price = _parse_price(soup)
        if price:
            log.info("scrape_bsr: ASIN %s price → $%.2f", asin, price)
        else:
            log.warning("scrape_bsr: ASIN %s price not found", asin)

        graph_cfg = build_graph_config()
        graph = SmartScraperGraph(prompt=_PROMPT, source=html, config=graph_cfg)

        try:
            result = graph.run()
        except Exception as exc:
            log.warning("scrape_bsr: SmartScraperGraph failed for ASIN %s (attempt %d): %s", asin, attempt + 1, exc)
            continue

        raw = result.get("ranks") if isinstance(result, dict) else None
        if not raw:
            log.warning(
                "scrape_bsr: ASIN %s — no ranks in LLM response (attempt %d/%d); "
                "Amazon may have served a CAPTCHA or interstitial",
                asin, attempt + 1, 1 + max_retries,
            )
            continue

        ranks: list[BestSellerRank] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                ranks.append(BestSellerRank(
                    asin=asin,
                    rank=int(item.get("rank") or 0),
                    category=str(item.get("category") or ""),
                    price=price,
                ))
            except (TypeError, ValueError) as exc:
                log.debug("Skipping malformed rank item: %s | %s", item, exc)

        if ranks:
            return ranks

        log.warning(
            "scrape_bsr: ASIN %s — parsed 0 valid ranks from LLM output (attempt %d/%d)",
            asin, attempt + 1, 1 + max_retries,
        )

    log.error("scrape_bsr: ASIN %s — all %d attempt(s) exhausted, returning []", asin, 1 + max_retries)
    return []


def run() -> None:
    log.info("=== scrape_bsr job started ===")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    log.info("Run ID: %s", run_id)

    asins = [b["asin"] for b in BookRepo().load_active_books()]
    if not asins:
        log.info("No active ASINs in registry — skipping run")
        return

    log.info("Using SQLite registry (%d active ASINs)", len(asins))
    repo = BookRepo()
    total_saved = 0

    for idx, asin in enumerate(asins):
        if idx > 0:
            log.debug("Waiting %.1fs before next ASIN …", settings.REQUEST_DELAY)
            time.sleep(settings.REQUEST_DELAY)

        log.info("Scraping BSR for ASIN: %s", asin)
        ranks = _scrape_bsr(str(asin))
        log.info("ASIN %s → %d rank entries", asin, len(ranks))

        if ranks:
            saved = repo.save_bsr_snapshots(ranks)
            total_saved += saved
        else:
            log.warning("ASIN %s — no BSR data found", asin)

    log.info("=== scrape_bsr job finished — total saved: %d ===", total_saved)
