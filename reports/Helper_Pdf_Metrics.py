"""
Metric computation layer for the PDF report pipeline.

Owned here: MonthlyRow, BookMetricsData (producer is Helper_Pdf_Metrics.compute).
"""

from __future__ import annotations

import itertools
from datetime import date, datetime
from typing import NamedTuple, TypedDict

from utils.Formula_calculator import Formula
from utils.Repo_MonthlySummary import MonthlySummaryRepo
from utils.Repo_Snapshot import DailySnapshotRow
from reports.Helper_Pdf_Loader import BookRawData


class MonthlyRow(NamedTuple):
    label: str           # "Aug 2026"
    units_str: str       # "1,234"
    profit_str: str      # "$4,567.89"
    avg_str: str         # "$152.26" (avg daily profit for that month)
    days_with_data: int  # number of days with at least one snapshot row


class BookMetricsData(TypedDict):
    # carried through from BookRawData
    asin: str
    title: str
    profit_pct: float
    snapshot_rows: list[DailySnapshotRow]
    # derived series (same length as snapshot_rows, sliced to last DAYS entries for charts)
    dates: list[date]
    date_labels: list[str]           # "Aug 01" formatted
    units_per_day: list[int]
    profit_per_day: list[float]
    cumulative_units: list[int]
    cumulative_profit: list[float]
    # monthly summary (full history, complete months only)
    monthly_rows: list[MonthlyRow]


def aggregate_month(
    rows: list[DailySnapshotRow], profit_pct: float
) -> tuple[int, float, int]:
    """Aggregate one month's daily snapshot rows into (total_units, total_profit, days_with_data).

    Same units/profit formula as the daily series: Formula.estimated_units_per_day
    and Formula.daily_profit per row, summed.
    """
    total_units = 0
    total_profit = 0.0
    for row in rows:
        rank = row["rank"]
        price = row["price"] if row["price"] else 0.0
        total_units += Formula.estimated_units_per_day(rank)
        total_profit += Formula.daily_profit(rank, price, profit_pct)
    return total_units, total_profit, len(rows)


class Helper_Pdf_Metrics:
    """Computes derived metrics from raw book snapshot data.

    Usage
    -----
    ::

        data: BookMetricsData = Helper_Pdf_Metrics().compute(raw_data)
    """

    def __init__(self, monthly_repo: MonthlySummaryRepo | None = None) -> None:
        self._monthly_repo = monthly_repo or MonthlySummaryRepo()

    def compute(self, data: BookRawData) -> BookMetricsData:
        """Derive daily and monthly metrics from *data*.

        Parameters
        ----------
        data:
            Raw book data produced by ``Helper_Pdf_Loader.load()``.

        Returns
        -------
        BookMetricsData
            All fields from *data* plus derived series and monthly buckets.
        """
        rows: list[DailySnapshotRow] = data["snapshot_rows"]
        profit_pct = data["profit_pct"]

        dates: list[date] = []
        date_labels: list[str] = []
        units_per_day: list[int] = []
        profit_per_day: list[float] = []

        for row in rows:
            d = date.fromisoformat(row["date"])
            rank = row["rank"]
            price = row["price"] if row["price"] else 0.0

            estimated_units = Formula.estimated_units_per_day(rank)
            daily_profit = Formula.daily_profit(rank, price, profit_pct)

            dates.append(d)
            date_labels.append(d.strftime("%b %d"))
            units_per_day.append(estimated_units)
            profit_per_day.append(daily_profit)

        cumulative_units: list[int] = list(itertools.accumulate(units_per_day))
        cumulative_profit: list[float] = list(itertools.accumulate(profit_per_day))

        today = date.today()
        current_ym = (today.year, today.month)

        precomputed = self._monthly_repo.get_many(data["asin"])

        past_months = sorted({(d.year, d.month) for d in dates if (d.year, d.month) != current_ym})

        monthly_rows: list[MonthlyRow] = []
        for ym in past_months:
            stored = precomputed.get(ym)
            if stored is not None:
                total_units = stored["total_units"]
                total_profit = stored["total_profit"]
                days_with_data = stored["days_with_data"]
            else:
                month_rows = [row for row, d in zip(rows, dates) if (d.year, d.month) == ym]
                total_units, total_profit, days_with_data = aggregate_month(month_rows, profit_pct)

            avg_daily_profit = total_profit / days_with_data if days_with_data else 0.0
            label = datetime(ym[0], ym[1], 1).strftime("%b %Y")
            monthly_rows.append(
                MonthlyRow(
                    label=label,
                    units_str=f"{total_units:,}",
                    profit_str=f"${total_profit:,.2f}",
                    avg_str=f"${avg_daily_profit:,.2f}",
                    days_with_data=int(days_with_data),
                )
            )

        return BookMetricsData(
            asin=data["asin"],
            title=data["title"],
            profit_pct=profit_pct,
            snapshot_rows=rows,
            dates=dates,
            date_labels=date_labels,
            units_per_day=units_per_day,
            profit_per_day=profit_per_day,
            cumulative_units=cumulative_units,
            cumulative_profit=cumulative_profit,
            monthly_rows=monthly_rows,
        )
