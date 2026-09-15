"""
Job: scrape Amazon Best Seller Rank (BSR) for each target ASIN.

Flow per ASIN:
  1. utils.browser.fetch_page_html() fetches the fully-rendered product page.
  2. extract_price_from_html() parses the price directly from the buybox DOM
     (no LLM needed — uses aria-label selectors on .a-price elements).
  3. extract_bsr_html_fragment() carves out the smallest HTML block that
     contains the BSR entries (typically #detailBullets_feature_div, ~5 KB).
  4. SmartScraperGraph feeds only that fragment to the LLM for BSR extraction.
  5. Results are persisted to the bsr_snapshots SQLite table via BookRepo.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from scrapegraphai.graphs import SmartScraperGraph

from config import settings, build_graph_config
from jobs.monthly_summary import sync_missing_months
from utils.browser import extract_bsr_html_fragment, extract_price_from_html, fetch_page_html
from utils.logger import get_logger
from utils.registry import BookRepo
from utils.Repo_CronRunLog import CronRunLogRepo

log = get_logger(__name__)


@dataclass
class BestSellerRank:
    asin: str
    rank: int
    category: str
    price: float = 0.0
    scraped_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


_PROMPT = """
Extract ALL Best Sellers Rank entries visible in this Amazon product detail block.

Return a JSON object with one key:
  - "ranks" : an array of rank objects, each with:
      - rank     : integer rank number (e.g. 1523)
      - category : full category path string exactly as shown (e.g. "Books > Science")
"""

# Top-level store categories we want to keep — sub-category ranks are ignored.
_TOP_LEVEL_CATEGORIES = {"Kindle Store", "Audible Books & Originals", "Books"}


def _dump_fragment(asin: str, attempt: int, fragment: str, llm_result: object) -> None:
    """Write the HTML fragment and LLM result to data/debug/ for diagnosis."""
    try:
        out_dir = Path(settings.OUTPUT_DIR) / "debug"
        out_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        slug = re.sub(r"[^a-zA-Z0-9]", "_", asin)
        stem = f"bsr_fragment_{slug}_attempt{attempt}_{timestamp}"
        html_path = out_dir / f"{stem}.html"
        json_path = out_dir / f"{stem}_llm.txt"
        html_path.write_text(fragment, encoding="utf-8")
        json_path.write_text(str(llm_result), encoding="utf-8")
        log.warning(
            "scrape_bsr: debug fragment → %s  |  LLM output → %s",
            html_path, json_path,
        )
    except Exception as exc:
        log.debug("scrape_bsr: failed to dump debug fragment — %s", exc)


def _scrape_bsr(
    asin: str,
    *,
    retries: int | None = None,
    retry_delay: float | None = None,
) -> list[BestSellerRank]:
    """Fetch and parse the single top-level BSR entry for *asin*.

    Only the first rank whose category is exactly ``"Kindle Store"``,
    ``"Audible Books & Originals"``, or ``"Books"`` is kept; sub-category
    ranks are discarded.

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

        price = extract_price_from_html(html)
        if price:
            log.info("scrape_bsr: ASIN %s price → $%.2f (via DOM)", asin, price)
        else:
            last_known_price = BookRepo().load_last_known_price(asin)
            if last_known_price:
                price = last_known_price
                log.info(
                    "scrape_bsr: ASIN %s price not found in DOM — using last known price $%.2f",
                    asin, price,
                )
            else:
                log.warning("scrape_bsr: ASIN %s price not found in DOM (no prior price to fall back to)", asin)

        fragment = extract_bsr_html_fragment(html)
        log.debug(
            "scrape_bsr: ASIN %s — feeding %d-char fragment to LLM (full HTML was %d chars)",
            asin, len(fragment), len(html),
        )

        graph_cfg = build_graph_config()
        graph = SmartScraperGraph(prompt=_PROMPT, source=fragment, config=graph_cfg)

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
                cat = str(item.get("category") or "")
                if cat not in _TOP_LEVEL_CATEGORIES:
                    continue
                ranks.append(BestSellerRank(
                    asin=asin,
                    rank=int(item.get("rank") or 0),
                    category=cat,
                    price=price,
                ))
                break  # keep only the first top-level store rank
            except (TypeError, ValueError) as exc:
                log.debug("Skipping malformed rank item: %s | %s", item, exc)

        if ranks:
            return ranks

        log.warning(
            "scrape_bsr: ASIN %s — no top-level store rank found in LLM output (attempt %d/%d); "
            "expected a 'Kindle Store', 'Audible Books & Originals', or 'Books' entry",
            asin, attempt + 1, 1 + max_retries,
        )
        _dump_fragment(asin, attempt + 1, fragment, result)

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
    cron_run_log_repo = CronRunLogRepo()
    total_saved = 0

    for idx, asin in enumerate(asins):
        if idx > 0:
            log.debug("Waiting %.1fs before next ASIN …", settings.REQUEST_DELAY)
            time.sleep(settings.REQUEST_DELAY)

        log.info("Scraping BSR for ASIN: %s", asin)
        scrape_started_at = datetime.now(timezone.utc).isoformat()
        ranks = _scrape_bsr(str(asin))
        log.info("ASIN %s → %d rank entries", asin, len(ranks))

        if ranks:
            saved = repo.save_bsr_snapshots(ranks)
            total_saved += saved
            _log_cron_run(
                cron_run_log_repo,
                cron_type="scrape_bsr",
                asin=str(asin),
                trigger="cron",
                started_at=scrape_started_at,
                status="success",
                detail=f"{len(ranks)} rank(s) saved",
            )

            monthly_started_at = datetime.now(timezone.utc).isoformat()
            try:
                computed = sync_missing_months(asin)
                if computed:
                    log.info("ASIN %s — backfilled %d missing monthly summary month(s)", asin, computed)
                _log_cron_run(
                    cron_run_log_repo,
                    cron_type="monthly_summary",
                    asin=str(asin),
                    trigger="scrape_bsr",
                    started_at=monthly_started_at,
                    status="success",
                    detail=f"{computed} month(s) backfilled",
                )
            except Exception as exc:
                log.warning("ASIN %s — monthly summary sync failed (will retry next scrape): %s", asin, exc)
                _log_cron_run(
                    cron_run_log_repo,
                    cron_type="monthly_summary",
                    asin=str(asin),
                    trigger="scrape_bsr",
                    started_at=monthly_started_at,
                    status="failure",
                    detail=str(exc),
                )
        else:
            log.warning("ASIN %s — no BSR data found", asin)
            _log_cron_run(
                cron_run_log_repo,
                cron_type="scrape_bsr",
                asin=str(asin),
                trigger="cron",
                started_at=scrape_started_at,
                status="failure",
                detail="no BSR data found",
            )

    log.info("=== scrape_bsr job finished — total saved: %d ===", total_saved)


def _log_cron_run(
    repo: CronRunLogRepo,
    *,
    cron_type: str,
    asin: str | None,
    trigger: str,
    started_at: str,
    status: str,
    detail: str | None,
) -> None:
    """Write one cron_run_log row without letting a logging failure abort the job."""
    try:
        repo.save(
            cron_type,
            asin=asin,
            trigger=trigger,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc).isoformat(),
            status=status,
            detail=detail,
        )
    except Exception as exc:
        log.warning("Failed to write cron_run_log row for %s (asin=%s): %s", cron_type, asin, exc)
