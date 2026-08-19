"""Unit tests for utils/Repo_Snapshot.py — SnapshotRepo."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from jobs.scrape_bsr import BestSellerRank
from utils.registry import BookRepo
from utils.Repo_Snapshot import DailySnapshotRow, SnapshotRepo


def _make_repo(tmp_db: BookRepo) -> SnapshotRepo:
    """Return a SnapshotRepo pointed at the same DB as *tmp_db*."""
    return SnapshotRepo(db_path=tmp_db._db_path)


def _insert_rows(tmp_db: BookRepo, rows: list[BestSellerRank]) -> None:
    tmp_db.save_bsr_snapshots(rows)


def _snap(asin: str, rank: int, price: float, date_str: str) -> BestSellerRank:
    """Build a BestSellerRank with a full UTC ISO timestamp for *date_str* (YYYY-MM-DD)."""
    scraped_at = f"{date_str}T12:00:00+00:00"
    return BestSellerRank(
        asin=asin,
        rank=rank,
        category="Books > Business",
        price=price,
        scraped_at=scraped_at,
    )


# ---------------------------------------------------------------------------
# test_load_daily_snapshots_returns_empty_for_no_data
# ---------------------------------------------------------------------------


def test_load_daily_snapshots_returns_empty_for_no_data(tmp_db: BookRepo) -> None:
    """Fresh DB — load_daily_snapshots returns an empty list."""
    repo = _make_repo(tmp_db)
    result = repo.load_daily_snapshots("B000000000")
    assert result == []


# ---------------------------------------------------------------------------
# test_load_daily_snapshots_aggregates_by_date
# ---------------------------------------------------------------------------


def test_load_daily_snapshots_aggregates_by_date(tmp_db: BookRepo) -> None:
    """Two rows on the same date should produce exactly one DailySnapshotRow."""
    asin = "B000000001"
    _insert_rows(tmp_db, [
        _snap(asin, rank=100, price=9.99,  date_str="2026-08-01"),
        _snap(asin, rank=200, price=14.99, date_str="2026-08-01"),
    ])

    result = _make_repo(tmp_db).load_daily_snapshots(asin)

    assert len(result) == 1
    assert result[0]["date"] == "2026-08-01"


# ---------------------------------------------------------------------------
# test_load_daily_snapshots_uses_best_rank_per_day
# ---------------------------------------------------------------------------


def test_load_daily_snapshots_uses_best_rank_per_day(tmp_db: BookRepo) -> None:
    """Same-date rows with ranks 50 and 200 — result must have rank == 50."""
    asin = "B000000002"
    _insert_rows(tmp_db, [
        _snap(asin, rank=50,  price=9.99, date_str="2026-08-01"),
        _snap(asin, rank=200, price=9.99, date_str="2026-08-01"),
    ])

    result = _make_repo(tmp_db).load_daily_snapshots(asin)

    assert len(result) == 1
    assert result[0]["rank"] == 50


# ---------------------------------------------------------------------------
# test_load_daily_snapshots_uses_highest_price_per_day
# ---------------------------------------------------------------------------


def test_load_daily_snapshots_uses_highest_price_per_day(tmp_db: BookRepo) -> None:
    """Same-date rows with prices 9.99 and 14.99 — result must have price == 14.99."""
    asin = "B000000003"
    _insert_rows(tmp_db, [
        _snap(asin, rank=100, price=9.99,  date_str="2026-08-01"),
        _snap(asin, rank=100, price=14.99, date_str="2026-08-01"),
    ])

    result = _make_repo(tmp_db).load_daily_snapshots(asin)

    assert len(result) == 1
    assert result[0]["price"] == 14.99


# ---------------------------------------------------------------------------
# test_load_daily_snapshots_sorted_oldest_first
# ---------------------------------------------------------------------------


def test_load_daily_snapshots_sorted_oldest_first(tmp_db: BookRepo) -> None:
    """Rows inserted out of chronological order must come back oldest-first."""
    asin = "B000000004"
    _insert_rows(tmp_db, [
        _snap(asin, rank=300, price=9.99, date_str="2026-08-03"),
        _snap(asin, rank=100, price=9.99, date_str="2026-08-01"),
        _snap(asin, rank=200, price=9.99, date_str="2026-08-02"),
    ])

    result = _make_repo(tmp_db).load_daily_snapshots(asin)

    dates = [row["date"] for row in result]
    assert dates == ["2026-08-01", "2026-08-02", "2026-08-03"]


# ---------------------------------------------------------------------------
# test_load_daily_snapshots_days_window
# ---------------------------------------------------------------------------


def test_load_daily_snapshots_days_window(tmp_db: BookRepo) -> None:
    """days=5 on 10 daily rows must return exactly 5 DailySnapshotRows."""
    asin = "B000000005"
    rows = [
        _snap(asin, rank=100 + i, price=9.99, date_str=f"2026-08-{i + 1:02d}")
        for i in range(10)
    ]
    _insert_rows(tmp_db, rows)

    result = _make_repo(tmp_db).load_daily_snapshots(asin, days=5)

    assert len(result) == 5
    # Must be the 5 most recent days (oldest-first), not the 5 oldest.
    assert [row["date"] for row in result] == [
        "2026-08-06",
        "2026-08-07",
        "2026-08-08",
        "2026-08-09",
        "2026-08-10",
    ]


# ---------------------------------------------------------------------------
# test_load_daily_snapshots_days_zero_returns_all
# ---------------------------------------------------------------------------


def test_load_daily_snapshots_days_zero_returns_all(tmp_db: BookRepo) -> None:
    """days=0 must return all rows regardless of how many there are."""
    asin = "B000000006"
    rows = [
        _snap(asin, rank=100 + i, price=9.99, date_str=f"2026-08-{i + 1:02d}")
        for i in range(10)
    ]
    _insert_rows(tmp_db, rows)

    result = _make_repo(tmp_db).load_daily_snapshots(asin, days=0)

    assert len(result) == 10
