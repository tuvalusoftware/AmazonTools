"""
Snapshot repository — date-grouped BSR snapshot queries.

Owned here: DailySnapshotRow (producer is SnapshotRepo.load_daily_snapshots).
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import TypedDict

from config import settings


def _get_db_path() -> Path:
    """Return the configured SQLite database path."""
    return Path(settings.DB_PATH)


class DailySnapshotRow(TypedDict):
    date: str    # ISO date string "2026-08-01"
    rank: int    # best (lowest) rank seen that day
    price: float # highest price seen that day; 0.0 when unavailable


class SnapshotRepo:
    """Read-only repository for date-grouped BSR snapshot data.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file.  Defaults to ``settings.DB_PATH``.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path is not None else _get_db_path()
        self._lock = threading.Lock()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def load_daily_snapshots(self, asin: str, days: int = 90) -> list[DailySnapshotRow]:
        """Return date-grouped BSR rows for *asin*, oldest-first.

        Each row represents one calendar day:

        - ``rank``  — the best (lowest) rank seen that day
        - ``price`` — the highest price seen that day; ``0.0`` when unavailable

        Parameters
        ----------
        asin:
            Amazon ASIN to query.
        days:
            Maximum number of calendar days to return (counted backwards from
            the most recent scraped date).  Pass ``0`` or a very large number
            to return the full history.

        Returns
        -------
        list[DailySnapshotRow]
            Empty list when no rows exist.
        """
        conn = self._get_conn()
        try:
            if days and days > 0:
                rows = conn.execute(
                    """
                    SELECT DATE(scraped_at) AS date,
                           MIN(rank)        AS rank,
                           MAX(price)       AS price
                    FROM   bsr_snapshots
                    WHERE  asin = ?
                    GROUP  BY DATE(scraped_at)
                    ORDER  BY DATE(scraped_at) ASC
                    LIMIT  ?
                    """,
                    (asin, days),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT DATE(scraped_at) AS date,
                           MIN(rank)        AS rank,
                           MAX(price)       AS price
                    FROM   bsr_snapshots
                    WHERE  asin = ?
                    GROUP  BY DATE(scraped_at)
                    ORDER  BY DATE(scraped_at) ASC
                    """,
                    (asin,),
                ).fetchall()
        finally:
            conn.close()

        return [
            DailySnapshotRow(
                date=row["date"],
                rank=int(row["rank"]),
                price=float(row["price"]) if row["price"] is not None else 0.0,
            )
            for row in rows
        ]
