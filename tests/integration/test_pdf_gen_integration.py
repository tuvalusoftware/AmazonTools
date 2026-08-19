"""
Integration test — visual preview of the full PDF report pipeline.

Purpose
-------
Run real Helper_Pdf_Metrics + Helper_Pdf_Renderer logic (no mocking of the
computation/rendering layers) against fully synthetic snapshot data — no DB,
no network, no LLM. Each scenario below covers a different data shape the
real pipeline can hit in production, and writes its own PDF to
tests/integration/pdf_gen_preview/ (gitignored) so a developer can open and
visually review it.

Run
---
    pytest tests/integration/test_pdf_gen_integration.py -m integration -v -s

The -s flag keeps stdout open so you can see each output path as it's
written:
    open tests/integration/pdf_gen_preview/*.pdf          # macOS
    xdg-open tests/integration/pdf_gen_preview/*.pdf     # Linux
"""

from __future__ import annotations

import random
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

import pytest
from matplotlib.backends.backend_pdf import PdfPages

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reports.Helper_Pdf_Loader import BookRawData  # noqa: E402
from reports.Helper_Pdf_Metrics import Helper_Pdf_Metrics  # noqa: E402
from reports.Helper_Pdf_Renderer import Helper_Pdf_Renderer  # noqa: E402
from utils.Repo_Snapshot import DailySnapshotRow  # noqa: E402

pytestmark = pytest.mark.integration

OUTPUT_DIR = Path(__file__).parent / "pdf_gen_preview"


# ---------------------------------------------------------------------------
# Scenario definitions — edit/add rows here to try new data shapes
# ---------------------------------------------------------------------------

@dataclass
class Scenario:
    name: str
    title: str
    profit_pct: float                       # raw percent, e.g. 70.0 for 70%
    days: int
    rank_fn: Callable[[int, int], int]       # (day_index, total_days) -> rank
    price_fn: Callable[[int, int], float] = field(default=lambda i, n: 4.99)


def _steady_growth_rank(i: int, n: int) -> int:
    """Rank steadily improves (drops) from 50,000 down to 300."""
    start, end = 50_000, 300
    return round(start - i * (start - end) / max(n - 1, 1))


def _volatile_rank(i: int, n: int) -> int:
    rng = random.Random(f"volatile-{i}")
    return rng.randint(500, 80_000)


def _oscillating_rank(i: int, n: int) -> int:
    rng = random.Random(f"oscillating-{i}")
    return rng.randint(1_000, 120_000)


SCENARIOS: list[Scenario] = [
    Scenario(
        name="steady_growth",
        title="The Growth Story",
        profit_pct=70.0,
        days=60,
        rank_fn=_steady_growth_rank,
    ),
    Scenario(
        name="volatile_ranking",
        title="Rollercoaster Rankings",
        profit_pct=35.0,
        days=45,
        rank_fn=_volatile_rank,
        price_fn=lambda i, n: 6.99,
    ),
    Scenario(
        name="minimal_two_days",
        title="Just Launched",
        profit_pct=70.0,
        days=2,                              # BookRawData's documented minimum
        rank_fn=lambda i, n: [20_000, 15_000][i],
        price_fn=lambda i, n: 9.99,
    ),
    Scenario(
        name="long_title",
        title=(
            "The Extraordinarily Long and Winding Title of a Sample Book That "
            "Really Tests Whether the Cover Page Wraps Text Correctly: A Subtitle "
            "About Testing Edge Cases in PDF Report Generation"
        ),
        profit_pct=50.0,
        days=30,
        rank_fn=_volatile_rank,
    ),
    Scenario(
        name="many_months_history",
        title="The Long Haul",
        profit_pct=60.0,
        days=400,                            # exercises many rows in the monthly table
        rank_fn=_oscillating_rank,
    ),
    Scenario(
        name="zero_price",
        title="Price Not Yet Scraped",
        profit_pct=70.0,
        days=30,
        rank_fn=_volatile_rank,
        price_fn=lambda i, n: 0.0,           # price selector missed on every scrape
    ),
    Scenario(
        name="extreme_high_rank",
        title="Deep Catalog Backlist Title",
        profit_pct=25.0,
        days=30,
        rank_fn=lambda i, n: 3_000_000,      # tiny estimated_units, near-flat charts
        price_fn=lambda i, n: 2.99,
    ),
    Scenario(
        name="vietnamese_title",
        title="Bí Quyết Thành Công – Hành Trình Từ Số 0 Đến Triệu Đô",
        profit_pct=45.0,
        days=20,
        rank_fn=_volatile_rank,
        price_fn=lambda i, n: 5.49,
    ),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_raw_data(scenario: Scenario) -> BookRawData:
    today = date.today()
    n = scenario.days
    rows: list[DailySnapshotRow] = []
    for i in range(n):
        d = today - timedelta(days=n - 1 - i)
        rows.append(
            DailySnapshotRow(
                date=d.isoformat(),
                rank=scenario.rank_fn(i, n),
                price=scenario.price_fn(i, n),
            )
        )
    return BookRawData(
        asin=f"B_{scenario.name.upper()}",
        title=scenario.title,
        profit_pct=scenario.profit_pct,
        snapshot_rows=rows,
    )


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.name for s in SCENARIOS])
def test_render_book_preview(scenario: Scenario) -> None:
    """
    Run the real Metrics + Renderer pipeline for one scenario and write the
    resulting PDF to OUTPUT_DIR for visual review.

    Structural assertions
    ----------------------
    - No exception is raised by the real (unmocked) compute/render pipeline.
    - The output PDF file exists and is non-trivially sized (matplotlib
      would still produce a tiny/near-empty file if rendering silently
      failed to draw anything).

    Visual inspection
    ------------------
    Open the printed path to check: cover page title wrapping, methodology
    text, grouped charts per page, captions, and the monthly table.
    """
    raw = _build_raw_data(scenario)
    metrics = Helper_Pdf_Metrics().compute(raw)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{scenario.name}.pdf"

    with PdfPages(str(output_path)) as pdf:
        Helper_Pdf_Renderer(pdf).render_book(metrics)

    assert output_path.exists(), f"PDF was not written for scenario {scenario.name!r}"
    size = output_path.stat().st_size
    assert size > 2_000, (
        f"PDF for scenario {scenario.name!r} is suspiciously small ({size} bytes) — "
        "rendering may have silently failed to draw content"
    )

    print(f"  [{scenario.name}] {size:,} bytes -> {output_path}")


def test_print_preview_summary() -> None:
    """Runs after all scenarios above (pytest preserves file declaration order) — prints a summary."""
    print(
        f"\n{'='*60}\n"
        f"  PDF report previews written to:\n"
        f"  {OUTPUT_DIR}\n"
        f"\n"
        f"  Open all of them:\n"
        f"    open {OUTPUT_DIR}/*.pdf         # macOS\n"
        f"    xdg-open {OUTPUT_DIR}/*.pdf     # Linux\n"
        f"{'='*60}"
    )
