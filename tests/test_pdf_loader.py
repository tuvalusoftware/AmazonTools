"""Unit tests for reports/Helper_Pdf_Loader.py — Helper_Pdf_Loader."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from reports.Helper_Pdf_Loader import BookRawData, Helper_Pdf_Loader
from utils.Repo_Snapshot import DailySnapshotRow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_snapshot_row(date: str) -> DailySnapshotRow:
    return DailySnapshotRow(date=date, rank=1000, price=14.99)


def _make_loader(active_books: list[dict], snapshot_rows: list[DailySnapshotRow]) -> tuple[Helper_Pdf_Loader, MagicMock]:
    """Return a Helper_Pdf_Loader with mocked repo and SnapshotRepo."""
    mock_repo = MagicMock()
    mock_repo.load_active_books.return_value = active_books
    loader = Helper_Pdf_Loader(repo=mock_repo)
    return loader, mock_repo


# ---------------------------------------------------------------------------
# test_load_returns_none_when_fewer_than_two_snapshots
# ---------------------------------------------------------------------------


def test_load_returns_none_when_fewer_than_two_snapshots() -> None:
    """load() returns None when SnapshotRepo yields only one row."""
    one_row = [_make_snapshot_row("2026-08-01")]

    loader, _ = _make_loader(
        active_books=[{"asin": "B000000001", "title": "My Book", "profit_pct": 0.70}],
        snapshot_rows=one_row,
    )

    with patch("reports.Helper_Pdf_Loader.SnapshotRepo") as MockSnapshotRepo:
        MockSnapshotRepo.return_value.load_daily_snapshots.return_value = one_row
        result = loader.load("B000000001", days=30)

    assert result is None


# ---------------------------------------------------------------------------
# test_load_returns_book_raw_data_with_correct_keys
# ---------------------------------------------------------------------------


def test_load_returns_book_raw_data_with_correct_keys() -> None:
    """Return value has exactly the keys: asin, title, profit_pct, snapshot_rows."""
    rows = [_make_snapshot_row(f"2026-08-0{i}") for i in range(1, 4)]

    loader, _ = _make_loader(
        active_books=[{"asin": "B000000002", "title": "Deep Work", "profit_pct": 0.70}],
        snapshot_rows=rows,
    )

    with patch("reports.Helper_Pdf_Loader.SnapshotRepo") as MockSnapshotRepo:
        MockSnapshotRepo.return_value.load_daily_snapshots.return_value = rows
        result = loader.load("B000000002", days=30)

    assert result is not None
    assert set(result.keys()) == {"asin", "title", "profit_pct", "snapshot_rows"}


# ---------------------------------------------------------------------------
# test_load_uses_profit_pct_from_tracked_books
# ---------------------------------------------------------------------------


def test_load_uses_profit_pct_from_tracked_books() -> None:
    """profit_pct in the returned dict equals the value from tracked_books."""
    rows = [_make_snapshot_row(f"2026-08-0{i}") for i in range(1, 3)]

    loader, _ = _make_loader(
        active_books=[{"asin": "B000000003", "title": "Essentialism", "profit_pct": 0.60}],
        snapshot_rows=rows,
    )

    with patch("reports.Helper_Pdf_Loader.SnapshotRepo") as MockSnapshotRepo:
        MockSnapshotRepo.return_value.load_daily_snapshots.return_value = rows
        result = loader.load("B000000003", days=30)

    assert result is not None
    assert result["profit_pct"] == 0.60


# ---------------------------------------------------------------------------
# test_load_falls_back_to_default_profit_pct
# ---------------------------------------------------------------------------


def test_load_falls_back_to_default_profit_pct() -> None:
    """When tracked_books has profit_pct=0 (falsy), fallback to 0.70."""
    rows = [_make_snapshot_row(f"2026-08-0{i}") for i in range(1, 3)]

    loader, _ = _make_loader(
        active_books=[{"asin": "B000000004", "title": "Atomic Habits", "profit_pct": 0}],
        snapshot_rows=rows,
    )

    with patch("reports.Helper_Pdf_Loader.SnapshotRepo") as MockSnapshotRepo:
        MockSnapshotRepo.return_value.load_daily_snapshots.return_value = rows
        result = loader.load("B000000004", days=30)

    assert result is not None
    assert result["profit_pct"] == 0.70


# ---------------------------------------------------------------------------
# test_load_snapshot_rows_are_oldest_first
# ---------------------------------------------------------------------------


def test_load_snapshot_rows_are_oldest_first() -> None:
    """snapshot_rows in the returned dict are ordered oldest-first."""
    unordered_rows = [
        _make_snapshot_row("2026-08-03"),
        _make_snapshot_row("2026-08-01"),
        _make_snapshot_row("2026-08-02"),
    ]

    loader, _ = _make_loader(
        active_books=[{"asin": "B000000005", "title": "The Lean Startup", "profit_pct": 0.70}],
        snapshot_rows=unordered_rows,
    )

    with patch("reports.Helper_Pdf_Loader.SnapshotRepo") as MockSnapshotRepo:
        MockSnapshotRepo.return_value.load_daily_snapshots.return_value = unordered_rows
        result = loader.load("B000000005", days=30)

    assert result is not None
    dates = [row["date"] for row in result["snapshot_rows"]]
    assert dates == ["2026-08-01", "2026-08-02", "2026-08-03"]
