"""Unit tests for reports/Helper_Pdf_Metrics.py — Helper_Pdf_Metrics."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from reports.Helper_Pdf_Loader import BookRawData
from reports.Helper_Pdf_Metrics import Helper_Pdf_Metrics
from utils.Formula_calculator import Formula
from utils.Repo_Snapshot import DailySnapshotRow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row(date_str: str, rank: int = 5000, price: float = 9.99) -> DailySnapshotRow:
    return DailySnapshotRow(date=date_str, rank=rank, price=price)


def _make_raw(rows: list[DailySnapshotRow], profit_pct: float = 70.0) -> BookRawData:
    return BookRawData(
        asin="B000TEST01",
        title="Test Book",
        profit_pct=profit_pct,
        snapshot_rows=rows,
    )


def _past_date(days_ago: int) -> str:
    """Return an ISO date string that is *days_ago* days before today."""
    return (date.today() - timedelta(days=days_ago)).isoformat()


def _date_in_complete_month(year: int, month: int, day: int = 15) -> str:
    """Return ISO string for a date in a guaranteed-complete month."""
    return date(year, month, day).isoformat()


class _FakeMonthlyRepo:
    """Stub MonthlySummaryRepo — returns a fixed mapping regardless of asin."""

    def __init__(self, summaries: dict[tuple[int, int], dict]) -> None:
        self._summaries = summaries

    def get_many(self, asin: str) -> dict[tuple[int, int], dict]:
        return self._summaries


_EMPTY_MONTHLY_REPO = _FakeMonthlyRepo({})


# ---------------------------------------------------------------------------
# test_compute_returns_book_metrics_data
# ---------------------------------------------------------------------------


def test_compute_returns_book_metrics_data() -> None:
    """Result contains all expected BookMetricsData keys."""
    rows = [_row(_past_date(40 - i)) for i in range(5)]
    result = Helper_Pdf_Metrics(_EMPTY_MONTHLY_REPO).compute(_make_raw(rows))

    expected_keys = {
        "asin", "title", "profit_pct", "snapshot_rows",
        "dates", "date_labels",
        "units_per_day", "profit_per_day",
        "cumulative_units", "cumulative_profit",
        "monthly_rows",
    }
    assert expected_keys.issubset(result.keys())


# ---------------------------------------------------------------------------
# test_compute_units_per_day_uses_power_law
# ---------------------------------------------------------------------------


def test_compute_units_per_day_uses_power_law() -> None:
    """units_per_day matches max(1, round(10_000 / rank^0.70))."""
    rank = 10_000
    rows = [_row(_past_date(5), rank=rank)]
    result = Helper_Pdf_Metrics(_EMPTY_MONTHLY_REPO).compute(_make_raw(rows))

    expected = max(1, round(10_000 / 10_000 ** 0.70))
    assert result["units_per_day"][0] == expected


# ---------------------------------------------------------------------------
# test_compute_daily_profit_uses_snapshot_price
# ---------------------------------------------------------------------------


def test_compute_daily_profit_uses_snapshot_price() -> None:
    """profit_per_day[i] == estimated_units * price * (profit_pct / 100)."""
    rank = 1_000
    price = 10.0
    profit_pct = 70.0

    rows = [_row(_past_date(5), rank=rank, price=price)]
    result = Helper_Pdf_Metrics(_EMPTY_MONTHLY_REPO).compute(_make_raw(rows, profit_pct=profit_pct))

    estimated_units = Formula.estimated_units_per_day(rank)
    expected = estimated_units * price * (profit_pct / 100.0)
    assert result["profit_per_day"][0] == pytest.approx(expected)


# ---------------------------------------------------------------------------
# test_compute_cumulative_units_is_running_total
# ---------------------------------------------------------------------------


def test_compute_cumulative_units_is_running_total() -> None:
    """cumulative_units is a running total of units_per_day."""
    # Choose ranks whose estimated_units_per_day are easy to predict.
    # rank=10_000 → max(1, round(10_000/10_000^0.70)) = max(1, round(1.0)) = 1
    # rank=1 → max(1, round(10_000/1^0.70)) = 10_000
    # Use ranks that give exactly 3 and 5 after the power law, or just
    # check the invariant directly without hard-coding the values.
    rows = [
        _row(_past_date(6), rank=5_000),
        _row(_past_date(5), rank=3_000),
    ]
    result = Helper_Pdf_Metrics(_EMPTY_MONTHLY_REPO).compute(_make_raw(rows))

    u = result["units_per_day"]
    cu = result["cumulative_units"]
    assert cu[0] == u[0]
    assert cu[1] == u[0] + u[1]


# ---------------------------------------------------------------------------
# test_compute_monthly_rows_excludes_current_month
# ---------------------------------------------------------------------------


def test_compute_monthly_rows_excludes_current_month() -> None:
    """Rows that fall in the current (partial) month produce no monthly_rows."""
    today = date.today()
    rows = [
        DailySnapshotRow(
            date=date(today.year, today.month, max(1, today.day - i)).isoformat(),
            rank=5000,
            price=9.99,
        )
        for i in range(5)
        if max(1, today.day - i) >= 1
    ]
    result = Helper_Pdf_Metrics(_EMPTY_MONTHLY_REPO).compute(_make_raw(rows))
    assert result["monthly_rows"] == []


# ---------------------------------------------------------------------------
# test_compute_monthly_rows_includes_all_complete_months
# ---------------------------------------------------------------------------


def test_compute_monthly_rows_includes_all_complete_months() -> None:
    """All complete past months appear in monthly_rows (one entry each)."""
    rows = [
        _row(_date_in_complete_month(2026, 3, 15)),
        _row(_date_in_complete_month(2026, 4, 10)),
        _row(_date_in_complete_month(2026, 5, 20)),
    ]
    result = Helper_Pdf_Metrics(_EMPTY_MONTHLY_REPO).compute(_make_raw(rows))
    assert len(result["monthly_rows"]) == 3


# ---------------------------------------------------------------------------
# test_compute_monthly_row_label_format
# ---------------------------------------------------------------------------


def test_compute_monthly_row_label_format() -> None:
    """MonthlyRow.label is formatted as 'Mon YYYY' (e.g. 'Jul 2026')."""
    rows = [_row("2026-07-15", rank=5000, price=9.99)]
    result = Helper_Pdf_Metrics(_EMPTY_MONTHLY_REPO).compute(_make_raw(rows))

    labels = [mr.label for mr in result["monthly_rows"]]
    assert "Jul 2026" in labels


# ---------------------------------------------------------------------------
# test_compute_series_lengths_match_snapshot_rows
# ---------------------------------------------------------------------------


def test_compute_series_lengths_match_snapshot_rows() -> None:
    """All derived series have exactly the same length as snapshot_rows."""
    rows = [_row(_past_date(40 - i)) for i in range(7)]
    result = Helper_Pdf_Metrics(_EMPTY_MONTHLY_REPO).compute(_make_raw(rows))

    n = len(rows)
    assert len(result["dates"]) == n
    assert len(result["units_per_day"]) == n
    assert len(result["profit_per_day"]) == n
    assert len(result["cumulative_units"]) == n
    assert len(result["cumulative_profit"]) == n


# ---------------------------------------------------------------------------
# test_compute_monthly_row_uses_precomputed_summary_when_present
# ---------------------------------------------------------------------------


def test_compute_monthly_row_uses_precomputed_summary_when_present() -> None:
    """A month with a MonthlySummaryRepo hit uses the stored numbers verbatim,
    even though they differ from what live aggregation would produce."""
    rows = [_row(_date_in_complete_month(2026, 3, 15), rank=5000, price=9.99)]
    fake_repo = _FakeMonthlyRepo(
        {
            (2026, 3): {
                "total_units": 999999,
                "total_profit": 123456.78,
                "days_with_data": 42,
            }
        }
    )
    result = Helper_Pdf_Metrics(fake_repo).compute(_make_raw(rows))

    assert len(result["monthly_rows"]) == 1
    row = result["monthly_rows"][0]
    assert row.units_str == "999,999"
    assert row.profit_str == "$123,456.78"
    assert row.days_with_data == 42


# ---------------------------------------------------------------------------
# test_compute_monthly_row_falls_back_to_live_aggregation_when_missing
# ---------------------------------------------------------------------------


def test_compute_monthly_row_falls_back_to_live_aggregation_when_missing() -> None:
    """A month with no stored row falls back to live aggregation, matching
    pre-change behavior."""
    rank = 5000
    price = 9.99
    profit_pct = 70.0
    rows = [
        _row(_date_in_complete_month(2026, 3, 10), rank=rank, price=price),
        _row(_date_in_complete_month(2026, 3, 15), rank=rank, price=price),
    ]
    fake_repo = _FakeMonthlyRepo({})
    result = Helper_Pdf_Metrics(fake_repo).compute(_make_raw(rows, profit_pct=profit_pct))

    assert len(result["monthly_rows"]) == 1
    row = result["monthly_rows"][0]

    estimated_units = Formula.estimated_units_per_day(rank)
    daily_profit = Formula.daily_profit(rank, price, profit_pct)
    expected_units = estimated_units * 2
    expected_profit = daily_profit * 2

    assert row.units_str == f"{expected_units:,}"
    assert row.profit_str == f"${expected_profit:,.2f}"
    assert row.days_with_data == 2


# ---------------------------------------------------------------------------
# test_compute_current_month_excluded_even_if_stored
# ---------------------------------------------------------------------------


def test_compute_current_month_excluded_even_if_stored() -> None:
    """Current month is excluded from monthly_rows regardless of what
    MonthlySummaryRepo returns for it."""
    today = date.today()
    rows = [
        DailySnapshotRow(
            date=date(today.year, today.month, max(1, today.day - i)).isoformat(),
            rank=5000,
            price=9.99,
        )
        for i in range(3)
        if max(1, today.day - i) >= 1
    ]
    fake_repo = _FakeMonthlyRepo(
        {
            (today.year, today.month): {
                "total_units": 111,
                "total_profit": 222.0,
                "days_with_data": 3,
            }
        }
    )
    result = Helper_Pdf_Metrics(fake_repo).compute(_make_raw(rows))
    assert result["monthly_rows"] == []
