"""
Integration test — _scrape_bsr against live Amazon + live LLM.

Requirements before running
---------------------------
1. Playwright Chromium installed:
       playwright install chromium
2. Valid Amazon session saved at BROWSER_STATE_PATH (default: data/browser_state.json).
   If the session is missing or expired, run the login helper first:
       python -c "from utils.browser import login_session; login_session()"
3. LLM provider configured in .env (LLM_PROVIDER + matching API key / Ollama running).
4. Internet access.

Run
---
    pytest tests/integration/test_scrape_bsr_integration.py -m integration -v -s

The -s flag keeps stdout open so you can see rank/price data in real time.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

import pytest
from pytest import LogCaptureFixture

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.scrape_bsr import BestSellerRank, _scrape_bsr  # noqa: E402

log = logging.getLogger(__name__)

pytestmark = pytest.mark.integration

# Seconds to wait between parametrized test cases — reduces Amazon rate-limit
# risk when running all 3 ASINs back-to-back in a single pytest session.
_INTER_TEST_DELAY: float = 15.0

# ---------------------------------------------------------------------------
# Known ASINs: (title_label, asin)
# title_label is only used for display — not passed to _scrape_bsr.
# ---------------------------------------------------------------------------
KNOWN_ASINS = [
    ("Atomic Habits", "B07RFSSYBH"),
    ("The Lean Startup", "B005MM7HY8"),
    ("Deep Work", "B0189PVAWY"),
]

_test_counter = {"n": 0}


@pytest.fixture(autouse=True)
def _throttle_between_tests() -> None:
    """Insert a delay before every test except the first to avoid Amazon rate-limiting."""
    if _test_counter["n"] > 0:
        log.info("Waiting %.0fs before next ASIN request …", _INTER_TEST_DELAY)
        time.sleep(_INTER_TEST_DELAY)
    _test_counter["n"] += 1


@pytest.mark.parametrize("title, asin", KNOWN_ASINS)
def test_scrape_bsr_real(title: str, asin: str, caplog: LogCaptureFixture) -> None:
    """
    Call _scrape_bsr with a real ASIN.  Verifies:
    - Returns a non-empty list of BestSellerRank objects
    - Each entry has a positive rank, non-empty category, and non-negative price
    - The asin field on every entry matches the input
    """
    with caplog.at_level(logging.INFO):
        results = _scrape_bsr(asin)

    # --- structural assertions ---
    assert isinstance(results, list), "Result must be a list"
    assert len(results) > 0, (
        f"[{title}] Expected at least 1 BSR entry for ASIN {asin}, got 0. "
        "Check browser session or LLM config."
    )

    for r in results:
        assert isinstance(r, BestSellerRank), f"Each item must be BestSellerRank, got {type(r)}"
        assert r.asin == asin, f"asin mismatch: expected {asin}, got {r.asin}"
        assert r.rank > 0, f"rank must be positive, got {r.rank}"
        assert len(r.category) > 0, f"category must not be empty, got {r.category!r}"
        assert r.price >= 0.0, f"price must be non-negative, got {r.price}"

    # --- soft price check: log warning if price is 0 (selector may have missed) ---
    prices = [r.price for r in results]
    if all(p == 0.0 for p in prices):
        log.warning(
            "[%s] ASIN %s — all entries have price=0.0. "
            "Price selector may need updating.",
            title,
            asin,
        )

    # --- stdout summary for human inspection (-s flag) ---
    print(
        f"\n{'='*60}\n"
        f"  Title  : {title}\n"
        f"  ASIN   : {asin}\n"
        f"  Entries: {len(results)}\n"
    )
    for i, r in enumerate(results, 1):
        price_str = f"${r.price:.2f}" if r.price else "N/A"
        print(f"  [{i}] rank={r.rank:,}  price={price_str}  cat={r.category!r}")
    print("=" * 60)
