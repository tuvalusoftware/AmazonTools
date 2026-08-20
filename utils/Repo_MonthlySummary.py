"""
Monthly summary repository — read/write access to book_monthly_summary.

Owned here: MonthlySummary (producer is MonthlySummaryRepo.get / get_many).
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

from config import settings


def _get_db_path() -> Path:
    """Return the configured SQLite database path."""
    return Path(settings.DB_PATH)


class MonthlySummary(TypedDict):
    asin: str
    year: int
    month: int
    total_units: int
    total_profit: float
    days_with_data: int


class MonthlySummaryRepo:
    """Thread-safe SQLite repository for precomputed monthly profit summaries.

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

    def save(
        self,
        asin: str,
        year: int,
        month: int,
        total_units: int,
        total_profit: float,
        days_with_data: int,
    ) -> None:
        """Insert or overwrite the summary row for (asin, year, month).

        Idempotent — safe to call repeatedly for the same month (e.g. manual
        re-run of the monthly job); the existing row is replaced, not duplicated.
        """
        computed_at = datetime.now(timezone.utc).isoformat()
        with self._lock:
            conn = self._get_conn()
            try:
                with conn:
                    conn.execute(
                        """
                        INSERT INTO book_monthly_summary
                            (asin, year, month, total_units, total_profit, days_with_data, computed_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT (asin, year, month) DO UPDATE SET
                            total_units = excluded.total_units,
                            total_profit = excluded.total_profit,
                            days_with_data = excluded.days_with_data,
                            computed_at = excluded.computed_at
                        """,
                        (asin, year, month, total_units, total_profit, days_with_data, computed_at),
                    )
            finally:
                conn.close()

    def get(self, asin: str, year: int, month: int) -> MonthlySummary | None:
        """Return the precomputed summary for one (asin, year, month), or None
        if it hasn't been computed yet."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                """
                SELECT asin, year, month, total_units, total_profit, days_with_data
                FROM   book_monthly_summary
                WHERE  asin = ? AND year = ? AND month = ?
                """,
                (asin, year, month),
            ).fetchone()
        finally:
            conn.close()

        if row is None:
            return None
        return MonthlySummary(
            asin=row["asin"],
            year=int(row["year"]),
            month=int(row["month"]),
            total_units=int(row["total_units"]),
            total_profit=float(row["total_profit"]),
            days_with_data=int(row["days_with_data"]),
        )

    def get_many(self, asin: str) -> dict[tuple[int, int], MonthlySummary]:
        """Return every precomputed summary row for *asin*, keyed by (year, month)."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """
                SELECT asin, year, month, total_units, total_profit, days_with_data
                FROM   book_monthly_summary
                WHERE  asin = ?
                """,
                (asin,),
            ).fetchall()
        finally:
            conn.close()

        return {
            (int(row["year"]), int(row["month"])): MonthlySummary(
                asin=row["asin"],
                year=int(row["year"]),
                month=int(row["month"]),
                total_units=int(row["total_units"]),
                total_profit=float(row["total_profit"]),
                days_with_data=int(row["days_with_data"]),
            )
            for row in rows
        }
