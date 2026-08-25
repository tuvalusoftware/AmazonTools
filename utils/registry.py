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
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from config import settings

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS tracked_books (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT    NOT NULL,
    title         TEXT    NOT NULL,
    asin          TEXT    NOT NULL,
    profit_pct    REAL    NOT NULL,
    current_price REAL    NOT NULL,
    added_at      TEXT    NOT NULL,
    active        INTEGER NOT NULL DEFAULT 1,
    UNIQUE (email, asin)
);
"""

_MIGRATE_UNIQUE_ASIN_TO_EMAIL_ASIN = """
ALTER TABLE tracked_books RENAME TO _tracked_books_old;
CREATE TABLE tracked_books (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT    NOT NULL,
    title         TEXT    NOT NULL,
    asin          TEXT    NOT NULL,
    profit_pct    REAL    NOT NULL,
    current_price REAL    NOT NULL,
    added_at      TEXT    NOT NULL,
    active        INTEGER NOT NULL DEFAULT 1,
    UNIQUE (email, asin)
);
INSERT INTO tracked_books SELECT * FROM _tracked_books_old;
DROP TABLE _tracked_books_old;
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

_CREATE_MONTHLY_SUMMARY_TABLE = """
CREATE TABLE IF NOT EXISTS book_monthly_summary (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    asin           TEXT    NOT NULL,
    year           INTEGER NOT NULL,
    month          INTEGER NOT NULL,
    total_units    INTEGER NOT NULL,
    total_profit   REAL    NOT NULL,
    days_with_data INTEGER NOT NULL,
    computed_at    TEXT    NOT NULL,
    UNIQUE (asin, year, month)
);
"""

_CREATE_CRON_RUN_LOG_TABLE = """
CREATE TABLE IF NOT EXISTS cron_run_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    cron_type    TEXT    NOT NULL,
    asin         TEXT,
    trigger      TEXT    NOT NULL,
    started_at   TEXT    NOT NULL,
    finished_at  TEXT    NOT NULL,
    status       TEXT    NOT NULL,
    detail       TEXT
);

CREATE INDEX IF NOT EXISTS idx_cron_run_log_cron_type_started_at
    ON cron_run_log (cron_type, started_at);

CREATE INDEX IF NOT EXISTS idx_cron_run_log_asin
    ON cron_run_log (asin);

CREATE INDEX IF NOT EXISTS idx_cron_run_log_started_at
    ON cron_run_log (started_at);
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
                conn.executescript(_CREATE_MONTHLY_SUMMARY_TABLE)
                conn.executescript(_CREATE_CRON_RUN_LOG_TABLE)
            try:
                conn.execute(
                    "ALTER TABLE bsr_snapshots ADD COLUMN price REAL NOT NULL DEFAULT 0"
                )
                conn.commit()
            except sqlite3.OperationalError:
                pass  # column already exists

            # Migrate old schema: UNIQUE(asin) → UNIQUE(email, asin)
            # Detect by checking whether any unique index on tracked_books covers
            # only the 'asin' column (the old single-column constraint).
            needs_migration = False
            for (_idx_seq, idx_name, unique, _origin, _partial) in conn.execute(
                "PRAGMA index_list('tracked_books')"
            ).fetchall():
                if unique:
                    cols = [
                        r[2]
                        for r in conn.execute(
                            f"PRAGMA index_info('{idx_name}')"  # noqa: S608
                        ).fetchall()
                    ]
                    if cols == ["asin"]:
                        needs_migration = True
                        break
            if needs_migration:
                conn.executescript(_MIGRATE_UNIQUE_ASIN_TO_EMAIL_ASIN)
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    # Write operations                                                     #
    # ------------------------------------------------------------------ #

    def save_bsr_snapshots(self, records: Sequence[_BsrRecord]) -> int:
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
                            book.get("current_price", 0.0),
                            added_at,
                        ),
                    )
                return True
            except sqlite3.IntegrityError:
                # UNIQUE(email, asin) violation — check if the row is inactive
                row = conn.execute(
                    "SELECT active FROM tracked_books WHERE email = ? AND asin = ?",
                    (book["email"], book["asin"]),
                ).fetchone()
                if row and row["active"] == 0:
                    with conn:
                        conn.execute(
                            "UPDATE tracked_books SET active=1 WHERE email=? AND asin=?",
                            (book["email"], book["asin"]),
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

    def find_book_by_asin(self, asin: str) -> dict[str, object] | None:
        """Return any tracked_books row for *asin* (active or not), or None."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM tracked_books WHERE asin = ? ORDER BY active DESC LIMIT 1",
                (asin,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def load_last_known_price(self, asin: str) -> float | None:
        """Return the most recent non-zero price scraped for *asin*, or None."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT price FROM bsr_snapshots"
                " WHERE asin=? AND price > 0 ORDER BY scraped_at DESC LIMIT 1",
                (asin,),
            ).fetchone()
            return float(row["price"]) if row else None
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
