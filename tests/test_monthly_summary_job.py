"""Unit tests for jobs/monthly_summary.py — sync_missing_months + run()."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from jobs.monthly_summary import _months_between, _target_month, run, sync_missing_months
from utils.Formula_calculator import Formula

YEAR, MONTH = _target_month()


def _prev_month(year: int, month: int) -> tuple[int, int]:
    return (year, month - 1) if month > 1 else (year - 1, 12)


def _rows(ranks_prices: list[tuple[int, float]], year: int = YEAR, month: int = MONTH) -> list[dict]:
    return [
        {"date": f"{year:04d}-{month:02d}-{i+1:02d}", "rank": rank, "price": price}
        for i, (rank, price) in enumerate(ranks_prices)
    ]


def _expected(rows: list[dict], profit_pct: float) -> tuple[int, float, int]:
    total_units = sum(Formula.estimated_units_per_day(r["rank"]) for r in rows)
    total_profit = sum(Formula.daily_profit(r["rank"], r["price"], profit_pct) for r in rows)
    return total_units, total_profit, len(rows)


def _mocks():
    return MagicMock(), MagicMock(), MagicMock()


# ---------------------------------------------------------------------------
# sync_missing_months
# ---------------------------------------------------------------------------


def test_sync_missing_months_backfills_all_missing_months() -> None:
    """3 completed months of data, no precomputed rows at all — all 3 get saved."""
    y2, m2 = _prev_month(YEAR, MONTH)
    y1, m1 = _prev_month(y2, m2)

    snapshot_repo, book_repo, summary_repo = _mocks()
    snapshot_repo.get_data_month_range.return_value = (y1, m1, YEAR, MONTH)
    summary_repo.get.return_value = None
    rows = _rows([(1000, 14.99)])
    snapshot_repo.load_daily_snapshots_for_month.return_value = rows
    book_repo.find_book_by_asin.return_value = {"profit_pct": 65.0}

    computed = sync_missing_months(
        "ASIN_A", snapshot_repo=snapshot_repo, book_repo=book_repo, summary_repo=summary_repo,
    )

    assert computed == 3
    assert summary_repo.save.call_count == 3


def test_sync_missing_months_only_computes_missing_month() -> None:
    """Oldest 2 of 3 completed months already precomputed — only the 1 missing month saved."""
    y2, m2 = _prev_month(YEAR, MONTH)
    y1, m1 = _prev_month(y2, m2)

    snapshot_repo, book_repo, summary_repo = _mocks()
    snapshot_repo.get_data_month_range.return_value = (y1, m1, YEAR, MONTH)

    def get(asin, year, month):
        return None if (year, month) == (YEAR, MONTH) else {"total_units": 1}

    summary_repo.get.side_effect = get
    rows = _rows([(1000, 14.99)])
    snapshot_repo.load_daily_snapshots_for_month.return_value = rows
    book_repo.find_book_by_asin.return_value = {"profit_pct": 65.0}

    computed = sync_missing_months(
        "ASIN_A", snapshot_repo=snapshot_repo, book_repo=book_repo, summary_repo=summary_repo,
    )

    assert computed == 1
    summary_repo.save.assert_called_once()
    assert summary_repo.save.call_args.args[1:3] == (YEAR, MONTH)


def test_sync_missing_months_excludes_current_in_progress_month() -> None:
    """A data row in the current in-progress month is never included in the walk."""
    current_y, current_m = _target_month()
    # Simulate get_data_month_range including a row dated in the current (not-yet-complete) month
    next_y, next_m = (current_y, current_m + 1) if current_m < 12 else (current_y + 1, 1)

    snapshot_repo, book_repo, summary_repo = _mocks()
    snapshot_repo.get_data_month_range.return_value = (current_y, current_m, next_y, next_m)
    summary_repo.get.return_value = None
    snapshot_repo.load_daily_snapshots_for_month.return_value = _rows([(1000, 14.99)])
    book_repo.find_book_by_asin.return_value = {"profit_pct": 65.0}

    sync_missing_months(
        "ASIN_A", snapshot_repo=snapshot_repo, book_repo=book_repo, summary_repo=summary_repo,
    )

    saved_months = [c.args[1:3] for c in summary_repo.save.call_args_list]
    assert (next_y, next_m) not in saved_months


def test_sync_missing_months_up_to_date_is_noop() -> None:
    """ASIN fully up to date — save() not called, return value 0."""
    snapshot_repo, book_repo, summary_repo = _mocks()
    snapshot_repo.get_data_month_range.return_value = (YEAR, MONTH, YEAR, MONTH)
    summary_repo.get.return_value = {"total_units": 1}

    computed = sync_missing_months(
        "ASIN_A", snapshot_repo=snapshot_repo, book_repo=book_repo, summary_repo=summary_repo,
    )

    assert computed == 0
    summary_repo.save.assert_not_called()


def test_sync_missing_months_no_data_range_returns_zero() -> None:
    """get_data_month_range returning None short-circuits without touching MonthlySummaryRepo."""
    snapshot_repo, book_repo, summary_repo = _mocks()
    snapshot_repo.get_data_month_range.return_value = None

    computed = sync_missing_months(
        "ASIN_A", snapshot_repo=snapshot_repo, book_repo=book_repo, summary_repo=summary_repo,
    )

    assert computed == 0
    summary_repo.get.assert_not_called()
    summary_repo.save.assert_not_called()


def test_sync_missing_months_includes_unsubscribed_asin() -> None:
    rows = _rows([(2000, 10.0), (2100, 10.0)])

    snapshot_repo, book_repo, summary_repo = _mocks()
    snapshot_repo.get_data_month_range.return_value = (YEAR, MONTH, YEAR, MONTH)
    summary_repo.get.return_value = None
    snapshot_repo.load_daily_snapshots_for_month.return_value = rows
    book_repo.find_book_by_asin.return_value = {"profit_pct": 50.0, "active": 0}

    sync_missing_months(
        "ASIN_UNSUB", snapshot_repo=snapshot_repo, book_repo=book_repo, summary_repo=summary_repo,
    )

    expected = _expected(rows, 50.0)
    summary_repo.save.assert_called_once_with("ASIN_UNSUB", YEAR, MONTH, *expected)


def test_sync_missing_months_falls_back_to_default_profit_pct_when_no_tracked_books_row() -> None:
    rows = _rows([(3000, 8.0)])

    snapshot_repo, book_repo, summary_repo = _mocks()
    snapshot_repo.get_data_month_range.return_value = (YEAR, MONTH, YEAR, MONTH)
    summary_repo.get.return_value = None
    snapshot_repo.load_daily_snapshots_for_month.return_value = rows
    book_repo.find_book_by_asin.return_value = None

    sync_missing_months(
        "ASIN_UNKNOWN", snapshot_repo=snapshot_repo, book_repo=book_repo, summary_repo=summary_repo,
    )

    expected = _expected(rows, 70.0)  # _DEFAULT_PROFIT_PCT
    summary_repo.save.assert_called_once_with("ASIN_UNKNOWN", YEAR, MONTH, *expected)


def test_months_between_is_inclusive() -> None:
    assert _months_between((2026, 11), (2027, 2)) == [
        (2026, 11), (2026, 12), (2027, 1), (2027, 2),
    ]


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------


def test_run_covers_all_asins_and_sums_computed_counts() -> None:
    with patch("jobs.monthly_summary.SnapshotRepo") as MockSnapshotRepo, \
         patch("jobs.monthly_summary.BookRepo"), \
         patch("jobs.monthly_summary.MonthlySummaryRepo"), \
         patch("jobs.monthly_summary.sync_missing_months") as mock_sync:

        MockSnapshotRepo.return_value.list_asins_that_have_data.return_value = ["ASIN_A", "ASIN_B"]
        mock_sync.side_effect = [2, 0]

        run()

    assert mock_sync.call_count == 2
    called_asins = [c.args[0] for c in mock_sync.call_args_list]
    assert called_asins == ["ASIN_A", "ASIN_B"]
