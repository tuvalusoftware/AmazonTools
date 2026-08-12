"""
Job: scrape Amazon Best Seller Rank (BSR) for each target ASIN.

Flow per ASIN:
  1. utils.browser.fetch_page_html() fetches the fully-rendered product page.
  2. The HTML is passed to SmartScraperGraph so the LLM extracts BSR data.
  3. Results are saved via utils.storage.save_results().
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from scrapegraphai.graphs import SmartScraperGraph

from config import settings, build_graph_config
from utils.browser import fetch_page_html
from utils.logger import get_logger
from utils.storage import save_results

log = get_logger(__name__)


@dataclass
class BestSellerRank:
    asin: str
    rank: int
    category: str
    scraped_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


_PROMPT = """
Extract ALL Best Sellers Rank entries visible on this Amazon product page.
Return a JSON object with a single key "ranks" containing an array.
Each element must have:
  - rank     : the integer rank number (e.g. 1523)
  - category : the full category path string exactly as shown (e.g. "Books > Science")
"""


def _scrape_bsr(asin: str) -> list[BestSellerRank]:
    url = settings.AMAZON_PRODUCT_URL.format(asin=asin)
    log.debug("Fetching ASIN %s: %s", asin, url)

    html = fetch_page_html(url)
    if not html:
        log.warning("Could not fetch HTML for ASIN %s", asin)
        return []

    graph_cfg = build_graph_config()
    graph = SmartScraperGraph(
        prompt=_PROMPT,
        source=html,
        config=graph_cfg,
    )

    try:
        result: dict = graph.run()
    except Exception as exc:
        log.warning("SmartScraperGraph failed for ASIN %s: %s", asin, exc)
        return []

    raw = result.get("ranks") if isinstance(result, dict) else None
    if not raw:
        log.debug("No ranks found in result for ASIN %s", asin)
        return []

    ranks: list[BestSellerRank] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            ranks.append(BestSellerRank(
                asin=asin,
                rank=int(item.get("rank") or 0),
                category=str(item.get("category") or ""),
            ))
        except (TypeError, ValueError) as exc:
            log.debug("Skipping malformed rank item: %s | %s", item, exc)

    return ranks


def run() -> None:
    log.info("=== scrape_bsr job started ===")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    log.info("Run ID: %s", run_id)
    total_saved = 0

    for asin in settings.asins:
        log.info("Scraping BSR for ASIN: %s", asin)
        ranks = _scrape_bsr(asin)
        log.info("ASIN %s → %d rank entries", asin, len(ranks))

        if ranks:
            saved = save_results(asin, ranks)
            total_saved += saved
        else:
            log.warning("ASIN %s — no BSR data found", asin)

    log.info("=== scrape_bsr job finished — total saved: %d ===", total_saved)
