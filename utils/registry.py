"""
SQLite-backed book registry.

Tables
------
tracked_books  — one row per (email, asin) pair.
  active=1: currently tracked.
  active=0: unsubscribed (retained for history).
bsr_snapshots  — append-only rank history; one row per rank/category per scrape run.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from config import settings

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS tracked_books (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT    NOT NULL,
    title         TEXT    NOT NULL,
    asin          TEXT    NOT NULL UNIQUE,
    profit_pct    REAL    NOT NULL,
    current_price REAL    NOT NULL,
    added_at      TEXT    NOT NULL,
    active        INTEGER NOT NULL DEFAULT 1
);
"""

_CREATE_BSR_SNAPSHOTS_TABLE = """
CREATE TABLE IF NOT EXISTS bsr_snapshots (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    asin       TEXT    NOT NULL,
    rank       INTEGER NOT NULL,
    category   TEXT    NOT NULL,
    price      REAL    NOT NULL DEFAULT 0,
    scraped_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bsr_snapshots_asin_scraped
    ON bsr_snapshots (asin, scraped_at DESC);
"""


class _BsrRecord(Protocol):
    asin: str
    rank: int
    category: str
    price: float
    scraped_at: str


class BookRepo:
    """Thread-safe SQLite repository for tracked books.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file.  Defaults to ``settings.DB_PATH``.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path is not None else Path(settings.DB_PATH)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------ #
    # Schema                                                               #
    # ------------------------------------------------------------------ #

    def init_db(self) -> None:
        """Create parent dirs and all tables if they do not exist."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._get_conn()
        try:
            with conn:
                conn.execute(_CREATE_TABLE)
                conn.executescript(_CREATE_BSR_SNAPSHOTS_TABLE)
            try:
                conn.execute(
                    "ALTER TABLE bsr_snapshots ADD COLUMN price REAL NOT NULL DEFAULT 0"
                )
                conn.commit()
            except sqlite3.OperationalError:
                pass  # column already exists
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    # Write operations                                                     #
    # ------------------------------------------------------------------ #

    def save_bsr_snapshots(self, records: list[_BsrRecord]) -> int:
        """Insert BSR snapshot records into bsr_snapshots.

        Accepts any objects with ``.asin``, ``.rank``, ``.category``,
        ``.price``, ``.scraped_at`` attributes (e.g. ``BestSellerRank`` dataclass instances).

        Returns the number of rows inserted.
        """
        rows = [
            (r.asin, r.rank, r.category, r.price, r.scraped_at)
            for r in records
        ]
        if not rows:
            return 0
        with self._lock:
            conn = self._get_conn()
            try:
                with conn:
                    conn.executemany(
                        "INSERT INTO bsr_snapshots (asin, rank, category, price, scraped_at) VALUES (?, ?, ?, ?, ?)",
                        rows,
                    )
                return len(rows)
            finally:
                conn.close()

    def register_book(self, book: dict[str, object]) -> bool:
        """Insert a new book record or reactivate an unsubscribed one.

        Expected keys: email, title, asin, profit_pct, current_price.

        Returns
        -------
        True   — newly inserted OR reactivated from active=0.
        False  — already active (duplicate); no change made.
        """
        added_at = datetime.now(timezone.utc).isoformat()

        with self._lock:
            conn = self._get_conn()
            try:
                with conn:
                    conn.execute(
                        """
                        INSERT INTO tracked_books
                            (email, title, asin, profit_pct, current_price, added_at, active)
                        VALUES (?, ?, ?, ?, ?, ?, 1)
                        """,
                        (
                            book["email"],
                            book["title"],
                            book["asin"],
                            book["profit_pct"],
                            book["current_price"],
                            added_at,
                        ),
                    )
                return True
            except sqlite3.IntegrityError:
                # UNIQUE constraint on asin — check if inactive
                row = conn.execute(
                    "SELECT active FROM tracked_books WHERE asin = ?", (book["asin"],)
                ).fetchone()
                if row and row["active"] == 0:
                    with conn:
                        conn.execute(
                            "UPDATE tracked_books SET active=1 WHERE asin=?",
                            (book["asin"],),
                        )
                    return True
                return False
            finally:
                conn.close()

    def unsubscribe_book(self, email: str, asin: str) -> bool:
        """Deactivate a single book for a given email.

        Returns True if the row was updated, False if not found or already inactive.
        """
        with self._lock:
            conn = self._get_conn()
            try:
                with conn:
                    cursor = conn.execute(
                        """
                        UPDATE tracked_books
                        SET active = 0
                        WHERE email = ? AND asin = ? AND active = 1
                        """,
                        (email, asin),
                    )
                return cursor.rowcount > 0
            finally:
                conn.close()

    def unsubscribe_email(self, email: str) -> int:
        """Deactivate all active books for *email*.

        Returns the number of records deactivated.
        """
        with self._lock:
            conn = self._get_conn()
            try:
                with conn:
                    cursor = conn.execute(
                        "UPDATE tracked_books SET active = 0 WHERE email = ? AND active = 1",
                        (email,),
                    )
                return cursor.rowcount
            finally:
                conn.close()

    # ------------------------------------------------------------------ #
    # Read operations                                                      #
    # ------------------------------------------------------------------ #

    def load_active_books(self) -> list[dict[str, object]]:
        """Return all books with active=1 as plain dicts."""
        conn = self._get_conn()
        try:
            cursor = conn.execute("SELECT * FROM tracked_books WHERE active = 1")
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def load_latest_snapshot(self, asin: str) -> dict[str, object] | None:
        """Return the most recent BSR snapshot for *asin*, or None if no rows exist."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT rank, category, price, scraped_at FROM bsr_snapshots"
                " WHERE asin=? ORDER BY scraped_at DESC LIMIT 1",
                (asin,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def load_rank_history(self, asin: str, days: int = 7) -> list[dict[str, object]]:
        """Return up to *days* daily rank data points for *asin*, oldest-first.

        One entry per calendar day (lowest rank value wins when multiple
        snapshots share the same date).
        """
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT DATE(scraped_at) AS date, rank"
                " FROM bsr_snapshots"
                " WHERE asin=?"
                " ORDER BY scraped_at DESC"
                " LIMIT ?",
                (asin, days * 10),
            ).fetchall()
        finally:
            conn.close()

        seen: dict[str, int] = {}
        for row in rows:
            d, r = row["date"], row["rank"]
            if d not in seen or r < seen[d]:
                seen[d] = r

        sorted_days = sorted(seen.keys())[-days:]
        return [{"date": d, "rank": seen[d]} for d in sorted_days]
