"""
Data-loading layer for the PDF report pipeline.

Owned here: BookRawData (producer is Helper_Pdf_Loader.load).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, TypedDict

from utils.Repo_Snapshot import DailySnapshotRow, SnapshotRepo

if TYPE_CHECKING:
    from utils.registry import BookRepo

logger = logging.getLogger(__name__)

_DEFAULT_PROFIT_PCT = 0.70


class BookRawData(TypedDict):
    asin: str
    title: str
    profit_pct: float                        # e.g. 0.70
    snapshot_rows: list[DailySnapshotRow]    # oldest-first; at least 2 entries guaranteed


class Helper_Pdf_Loader:
    """Loads raw book data from the database for the PDF report pipeline.

    Parameters
    ----------
    repo:
        A ``BookRepo`` instance used to query ``tracked_books`` and
        delegate snapshot retrieval to ``SnapshotRepo``.
    """

    def __init__(self, repo: BookRepo) -> None:
        self._repo = repo

    def load(self, asin: str, days: int) -> BookRawData | None:
        """Load raw book data for *asin*.

        Parameters
        ----------
        asin:
            The ASIN to load data for.
        days:
            Rolling window length (passed through to the snapshot query).

        Returns
        -------
        BookRawData | None
            ``None`` when fewer than 2 snapshot rows exist (caller should log a
            WARNING and skip this ASIN).
        """
        active_books = self._repo.load_active_books()
        book_row = next((b for b in active_books if b["asin"] == asin), None)

        if book_row is not None:
            title = str(book_row.get("title") or "")
            raw_pct = book_row.get("profit_pct")
            profit_pct = float(raw_pct) if isinstance(raw_pct, (int, float)) and raw_pct else _DEFAULT_PROFIT_PCT
        else:
            title = asin
            profit_pct = _DEFAULT_PROFIT_PCT

        snapshot_rows = SnapshotRepo().load_daily_snapshots(asin, days)

        if len(snapshot_rows) < 2:
            return None

        snapshot_rows = sorted(snapshot_rows, key=lambda r: r["date"])

        return BookRawData(
            asin=asin,
            title=title,
            profit_pct=profit_pct,
            snapshot_rows=snapshot_rows,
        )
