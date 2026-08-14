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
from pathlib import Path

from matplotlib.backends.backend_pdf import PdfPages

from reports.Helper_Pdf_Loader import Helper_Pdf_Loader
from reports.Helper_Pdf_Metrics import Helper_Pdf_Metrics
from reports.Helper_Pdf_Renderer import Helper_Pdf_Renderer
from utils.registry import BookRepo

# ── Tuneable constants ─────────────────────────────────────────────────────────
DAYS = 30           # rolling window queried from bsr_snapshots
OUTPUT_PATH = Path(__file__).parent / "book_performance_report.pdf"

logger = logging.getLogger(__name__)


class Service_Pdf_GenFromAsin:
    """Generate a multi-page PDF performance report from live DB data.

    Parameters
    ----------
    asin_filter:
        Restrict the report to a single ASIN.  ``None`` (default) generates
        one section per active book in ``tracked_books``.
    output_path:
        Destination for the PDF file.  Falls back to ``OUTPUT_PATH`` constant.
    """

    def __init__(
        self,
        asin_filter: str | None = None,
        output_path: Path | None = None,
    ) -> None:
        self._asin_filter = asin_filter
        self._output_path = output_path or OUTPUT_PATH

    def run(self) -> Path:
        """Build and write the PDF report.

        Returns
        -------
        Path
            Resolved path of the written PDF file.
        """
        repo = BookRepo()

        if self._asin_filter:
            asins = [self._asin_filter]
        else:
            asins = [str(book["asin"]) for book in repo.load_active_books()]

        output = self._output_path.resolve()

        with PdfPages(str(output)) as pdf:
            for asin in asins:
                raw = Helper_Pdf_Loader(repo).load(asin, DAYS)
                if raw is None:
                    logger.warning("Skipping ASIN %s — fewer than 2 snapshot rows", asin)
                    continue
                metrics = Helper_Pdf_Metrics().compute(raw)
                Helper_Pdf_Renderer(pdf).render_book(metrics)

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
