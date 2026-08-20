"""Unit tests for jobs/monthly_summary.py — the monthly summary cron job."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from jobs.monthly_summary import _target_month, run
from utils.Formula_calculator import Formula

YEAR, MONTH = _target_month()


def _rows(ranks_prices: list[tuple[int, float]]) -> list[dict]:
    return [
        {"date": f"{YEAR:04d}-{MONTH:02d}-{i+1:02d}", "rank": rank, "price": price}
        for i, (rank, price) in enumerate(ranks_prices)
    ]


def _expected(rows: list[dict], profit_pct: float) -> tuple[int, float, int]:
    total_units = sum(Formula.estimated_units_per_day(r["rank"]) for r in rows)
    total_profit = sum(Formula.daily_profit(r["rank"], r["price"], profit_pct) for r in rows)
    return total_units, total_profit, len(rows)


# ---------------------------------------------------------------------------
# test_run_saves_aggregated_summary_per_asin
# ---------------------------------------------------------------------------


def test_run_saves_aggregated_summary_per_asin() -> None:
    rows_a = _rows([(1000, 14.99), (1200, 14.99), (900, 12.99)])
    rows_b = _rows([(5000, 9.99), (4800, 9.99)])

    with patch("jobs.monthly_summary.SnapshotRepo") as MockSnapshotRepo, \
         patch("jobs.monthly_summary.BookRepo") as MockBookRepo, \
         patch("jobs.monthly_summary.MonthlySummaryRepo") as MockSummaryRepo:

        MockSnapshotRepo.return_value.list_asins_that_have_data.return_value = ["ASIN_A", "ASIN_B"]

        def load_month(asin, year, month):
            return {"ASIN_A": rows_a, "ASIN_B": rows_b}[asin]

        MockSnapshotRepo.return_value.load_daily_snapshots_for_month.side_effect = load_month
        MockBookRepo.return_value.find_book_by_asin.side_effect = lambda asin: {
            "ASIN_A": {"profit_pct": 65.0, "active": 1},
            "ASIN_B": {"profit_pct": 70.0, "active": 1},
        }[asin]

        run()

    expected_a = _expected(rows_a, 65.0)
    expected_b = _expected(rows_b, 70.0)

    save_calls = {c.args[0]: c.args for c in MockSummaryRepo.return_value.save.call_args_list}
    assert save_calls["ASIN_A"] == ("ASIN_A", YEAR, MONTH, *expected_a)
    assert save_calls["ASIN_B"] == ("ASIN_B", YEAR, MONTH, *expected_b)
    assert MockSummaryRepo.return_value.save.call_count == 2


# ---------------------------------------------------------------------------
# test_run_skips_asin_with_no_rows_in_target_month
# ---------------------------------------------------------------------------


def test_run_skips_asin_with_no_rows_in_target_month() -> None:
    with patch("jobs.monthly_summary.SnapshotRepo") as MockSnapshotRepo, \
         patch("jobs.monthly_summary.BookRepo") as MockBookRepo, \
         patch("jobs.monthly_summary.MonthlySummaryRepo") as MockSummaryRepo:

        MockSnapshotRepo.return_value.list_asins_that_have_data.return_value = ["ASIN_EMPTY"]
        MockSnapshotRepo.return_value.load_daily_snapshots_for_month.return_value = []

        run()

    MockBookRepo.return_value.find_book_by_asin.assert_not_called()
    MockSummaryRepo.return_value.save.assert_not_called()


# ---------------------------------------------------------------------------
# test_run_includes_unsubscribed_asin
# ---------------------------------------------------------------------------


def test_run_includes_unsubscribed_asin() -> None:
    rows = _rows([(2000, 10.0), (2100, 10.0)])

    with patch("jobs.monthly_summary.SnapshotRepo") as MockSnapshotRepo, \
         patch("jobs.monthly_summary.BookRepo") as MockBookRepo, \
         patch("jobs.monthly_summary.MonthlySummaryRepo") as MockSummaryRepo:

        MockSnapshotRepo.return_value.list_asins_that_have_data.return_value = ["ASIN_UNSUB"]
        MockSnapshotRepo.return_value.load_daily_snapshots_for_month.return_value = rows
        MockBookRepo.return_value.find_book_by_asin.return_value = {
            "profit_pct": 50.0,
            "active": 0,
        }

        run()

    expected = _expected(rows, 50.0)
    MockSummaryRepo.return_value.save.assert_called_once_with("ASIN_UNSUB", YEAR, MONTH, *expected)


# ---------------------------------------------------------------------------
# test_run_falls_back_to_default_profit_pct_when_no_tracked_books_row
# ---------------------------------------------------------------------------


def test_run_falls_back_to_default_profit_pct_when_no_tracked_books_row() -> None:
    rows = _rows([(3000, 8.0)])

    with patch("jobs.monthly_summary.SnapshotRepo") as MockSnapshotRepo, \
         patch("jobs.monthly_summary.BookRepo") as MockBookRepo, \
         patch("jobs.monthly_summary.MonthlySummaryRepo") as MockSummaryRepo:

        MockSnapshotRepo.return_value.list_asins_that_have_data.return_value = ["ASIN_UNKNOWN"]
        MockSnapshotRepo.return_value.load_daily_snapshots_for_month.return_value = rows
        MockBookRepo.return_value.find_book_by_asin.return_value = None

        run()

    expected = _expected(rows, 70.0)  # _DEFAULT_PROFIT_PCT
    MockSummaryRepo.return_value.save.assert_called_once_with("ASIN_UNKNOWN", YEAR, MONTH, *expected)
