"""
Integration test — search_asin against live Amazon.

Requirements before running
---------------------------
1. Playwright Chromium installed:
       playwright install chromium
2. Valid Amazon session saved at BROWSER_STATE_PATH (default: data/browser_state.json).
   If the session is missing or expired, run the login helper first:
       python -c "from utils.browser import login_session; login_session()"
3. Internet access.

Run
---
    pytest tests/integration/test_lookup_asin_integration.py -m integration -v -s

The -s flag keeps stdout open so you can see the logged ASIN in real time.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest
from pytest import LogCaptureFixture

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.lookup_asin import search_asin  # noqa: E402

log = logging.getLogger(__name__)

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Known books: (input_title, expected_asin)
# expected_asin is the canonical ASIN — used only as a cross-check reference.
# The test does NOT hard-fail on a mismatch; it logs a warning so you can
# decide whether Amazon returned a redirect/new edition.
# ---------------------------------------------------------------------------
KNOWN_BOOKS = [
    ("Atomic Habits", "B07RFSSYBH"),
    ("The Lean Startup", "B005MM7HY8"),
    ("Deep Work", "B0189PVAWY"),
]


@pytest.mark.parametrize("title, expected_asin", KNOWN_BOOKS)
def test_search_asin_real(title: str, expected_asin: str, caplog: LogCaptureFixture) -> None:
    """
    Call search_asin with a real title and verify the returned ASIN looks valid.
    Logs the actual ASIN so you can cross-check against Amazon manually.
    """
    with caplog.at_level(logging.INFO):
        result_title, asin = search_asin(title)

    # --- structural assertions (always enforced) ---
    assert result_title == title, "returned title must match input"
    assert len(asin) == 10, f"ASIN must be 10 characters, got: {asin!r}"
    assert asin.isalnum(), f"ASIN must be alphanumeric, got: {asin!r}"

    # --- cross-check log (soft warning, not a hard failure) ---
    if asin != expected_asin:
        log.warning(
            "[%s] Amazon returned ASIN %s — expected reference %s. "
            "Possible redirect or new edition. Verify manually at: "
            "https://www.amazon.com/dp/%s",
            title,
            asin,
            expected_asin,
            asin,
        )
    else:
        log.info(
            "[%s] ASIN matched: %s  ✓  https://www.amazon.com/dp/%s",
            title,
            asin,
            asin,
        )

    # Always print to stdout (visible with -s) for quick human inspection
    print(
        f"\n{'='*60}\n"
        f"  Title    : {title}\n"
        f"  Got ASIN : {asin}   → https://www.amazon.com/dp/{asin}\n"
        f"  Expected : {expected_asin}"
        + ("  ✓" if asin == expected_asin else "  ← MISMATCH (soft)")
        + f"\n{'='*60}"
    )
