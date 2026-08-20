"""
Cron run log repository — append-only write/query access to cron_run_log.

One row per unit of work per cron job invocation (see issues/4/main.md for
the granularity decision). Never upserted — every save() inserts a new row.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import TypedDict

from config import settings


class CronRunLogRow(TypedDict):
    id: int
    cron_type: str
    asin: str | None
    trigger: str
    started_at: str
    finished_at: str
    status: str
    detail: str | None


class CronRunLogRepo:
    """Thread-safe SQLite repository for the cron_run_log table.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file.  Defaults to ``settings.DB_PATH``.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path is not None else Path(settings.DB_PATH)
        self._lock = threading.Lock()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def save(
        self,
        cron_type: str,
        *,
        asin: str | None,
        trigger: str,
        started_at: str,
        finished_at: str,
        status: str,
        detail: str | None = None,
    ) -> None:
        """Insert one cron_run_log row. Every call inserts a new row — this is
        an append-only log, never an upsert."""
        with self._lock:
            conn = self._get_conn()
            try:
                with conn:
                    conn.execute(
                        """
                        INSERT INTO cron_run_log
                            (cron_type, asin, trigger, started_at, finished_at, status, detail)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (cron_type, asin, trigger, started_at, finished_at, status, detail),
                    )
            finally:
                conn.close()

    def query(
        self,
        *,
        cron_type: str | None = None,
        asin: str | None = None,
        status: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CronRunLogRow]:
        """Return cron_run_log rows matching every provided filter, newest
        (by started_at) first. All filters are optional and combine with AND;
        calling with no filters returns the most recent `limit` rows across
        every cron_type."""
        conditions: list[str] = []
        params: list[object] = []

        if cron_type is not None:
            conditions.append("cron_type = ?")
            params.append(cron_type)
        if asin is not None:
            conditions.append("asin = ?")
            params.append(asin)
        if status is not None:
            conditions.append("status = ?")
            params.append(status)
        if start_time is not None:
            conditions.append("started_at >= ?")
            params.append(start_time)
        if end_time is not None:
            conditions.append("started_at <= ?")
            params.append(end_time)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.extend([limit, offset])

        conn = self._get_conn()
        try:
            rows = conn.execute(
                f"""
                SELECT id, cron_type, asin, trigger, started_at, finished_at, status, detail
                FROM   cron_run_log
                {where_clause}
                ORDER  BY started_at DESC
                LIMIT  ? OFFSET ?
                """,  # noqa: S608
                params,
            ).fetchall()
        finally:
            conn.close()

        return [
            CronRunLogRow(
                id=int(row["id"]),
                cron_type=row["cron_type"],
                asin=row["asin"],
                trigger=row["trigger"],
                started_at=row["started_at"],
                finished_at=row["finished_at"],
                status=row["status"],
                detail=row["detail"],
            )
            for row in rows
        ]
