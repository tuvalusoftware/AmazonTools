"""
Entry point for the PDF performance report pipeline.

Usage
-----
Run all active books::

    python reports/Service_pdf_genFromAsin.py

Single ASIN::

    python reports/Service_pdf_genFromAsin.py --asin B0XXXXXXXX

Custom output path::

    python reports/Service_pdf_genFromAsin.py --output /tmp/report.pdf
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from matplotlib.backends.backend_pdf import PdfPages

from reports.Helper_Pdf_Loader import Helper_Pdf_Loader
from reports.Helper_Pdf_Metrics import Helper_Pdf_Metrics
from reports.Helper_Pdf_Renderer import Helper_Pdf_Renderer
from utils.registry import BookRepo
from utils.Repo_MonthlySummary import MonthlySummaryRepo

# ── Tuneable constants ─────────────────────────────────────────────────────────
# 0 = full history. Metrics.compute() needs full history to build a complete
# monthly profit table; Helper_Pdf_Renderer separately windows the daily/
# cumulative charts down to the most recent 30 days for readability.
DAYS = 0
OUTPUT_PATH = Path(__file__).parent / "book_performance_report.pdf"

logger = logging.getLogger(__name__)


class Service_Pdf_GenFromAsin:
    """Generate a multi-page PDF performance report from live DB data.

    Parameters
    ----------
    asin_filter:
        Restrict the report to a single ASIN, or to a list of ASINs (e.g. the
        books a single subscriber follows).  ``None`` (default) generates one
        section per active book in ``tracked_books``.
    output_path:
        Destination for the PDF file.  Falls back to ``OUTPUT_PATH`` constant.
    """

    def __init__(
        self,
        asin_filter: str | Sequence[str] | None = None,
        output_path: Path | None = None,
    ) -> None:
        self._asin_filter = asin_filter
        self._output_path = output_path or OUTPUT_PATH

    def run(self) -> Path | None:
        """Build and write the PDF report.

        Returns
        -------
        Path | None
            Resolved path of the written PDF file, or ``None`` if no book
            had enough snapshot data (≥2 rows) to include a section.
        """
        repo = BookRepo()
        monthly_repo = MonthlySummaryRepo()

        if self._asin_filter is None:
            asins = [str(book["asin"]) for book in repo.load_active_books()]
        elif isinstance(self._asin_filter, str):
            asins = [self._asin_filter]
        else:
            asins = [str(a) for a in self._asin_filter]

        output = self._output_path.resolve()

        included = 0
        with PdfPages(str(output)) as pdf:
            for asin in asins:
                raw = Helper_Pdf_Loader(repo).load(asin, DAYS)
                if raw is None:
                    logger.warning("Skipping ASIN %s — fewer than 2 snapshot rows", asin)
                    continue
                metrics = Helper_Pdf_Metrics(monthly_repo).compute(raw)
                Helper_Pdf_Renderer(pdf).render_book(metrics)
                included += 1

        if included == 0:
            output.unlink(missing_ok=True)
            logger.warning("No books had enough snapshot data — no PDF written")
            return None

        logger.info("PDF written to %s", output)
        return output


# ── CLI ────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a PDF BSR performance report from the live database.",
    )
    parser.add_argument(
        "--asin",
        metavar="ASIN",
        default=None,
        help="Restrict report to a single ASIN (default: all active books).",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        type=Path,
        default=None,
        help=f"Output PDF path (default: {OUTPUT_PATH}).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _parse_args()
    path = Service_Pdf_GenFromAsin(
        asin_filter=args.asin,
        output_path=args.output,
    ).run()
    print(f"PDF written to {path}")
