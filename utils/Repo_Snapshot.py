"""
Snapshot repository — date-grouped BSR snapshot queries.

Owned here: DailySnapshotRow (producer is SnapshotRepo.load_daily_snapshots).
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import date
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
                    SELECT date, rank, price
                    FROM (
                        SELECT DATE(scraped_at) AS date,
                               MIN(rank)        AS rank,
                               MAX(price)       AS price
                        FROM   bsr_snapshots
                        WHERE  asin = ?
                        GROUP  BY DATE(scraped_at)
                        ORDER  BY DATE(scraped_at) DESC
                        LIMIT  ?
                    )
                    ORDER BY date ASC
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

    def load_daily_snapshots_for_month(
        self, asin: str, year: int, month: int
    ) -> list[DailySnapshotRow]:
        """Return date-grouped BSR rows for *asin* restricted to one calendar month.

        Same per-day aggregation as ``load_daily_snapshots`` (best rank, highest
        price per day), oldest-first, but scoped to ``year``/``month`` instead of
        a rolling day-count window.

        Returns
        -------
        list[DailySnapshotRow]
            Empty list when no rows exist for that month.
        """
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """
                SELECT DATE(scraped_at) AS date,
                       MIN(rank)        AS rank,
                       MAX(price)       AS price
                FROM   bsr_snapshots
                WHERE  asin = ?
                  AND  strftime('%Y', scraped_at) = ?
                  AND  strftime('%m', scraped_at) = ?
                GROUP  BY DATE(scraped_at)
                ORDER  BY DATE(scraped_at) ASC
                """,
                (asin, f"{year:04d}", f"{month:02d}"),
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

    def get_data_month_range(self, asin: str) -> tuple[int, int, int, int] | None:
        """Return (start_year, start_month, end_year, end_month) spanning every
        calendar month that has at least one bsr_snapshots row for *asin*,
        inclusive on both ends. None if *asin* has no rows at all."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                """
                SELECT MIN(DATE(scraped_at)) AS first_date, MAX(DATE(scraped_at)) AS last_date
                FROM   bsr_snapshots
                WHERE  asin = ?
                """,
                (asin,),
            ).fetchone()
        finally:
            conn.close()

        if row is None or row["first_date"] is None:
            return None

        first = date.fromisoformat(row["first_date"])
        last = date.fromisoformat(row["last_date"])
        return (first.year, first.month, last.year, last.month)

    def list_asins_that_have_data(self) -> list[str]:
        """Return every distinct ASIN that has at least one row in bsr_snapshots."""
        conn = self._get_conn()
        try:
            rows = conn.execute("SELECT DISTINCT asin FROM bsr_snapshots").fetchall()
        finally:
            conn.close()

        return [row["asin"] for row in rows]
