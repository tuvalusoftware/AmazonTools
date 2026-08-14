"""
Metric computation layer for the PDF report pipeline.

Owned here: MonthlyRow, BookMetricsData (producer is Helper_Pdf_Metrics.compute).
"""

from __future__ import annotations

import itertools
from collections import defaultdict
from datetime import date, datetime
from typing import NamedTuple, TypedDict

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


class Helper_Pdf_Metrics:
    """Computes derived metrics from raw book snapshot data.

    Usage
    -----
    ::

        data: BookMetricsData = Helper_Pdf_Metrics().compute(raw_data)
    """

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

            estimated_units = max(1, round(10_000 / rank ** 0.70))
            daily_profit = estimated_units * price * profit_pct

            dates.append(d)
            date_labels.append(d.strftime("%b %d"))
            units_per_day.append(estimated_units)
            profit_per_day.append(daily_profit)

        cumulative_units: list[int] = list(itertools.accumulate(units_per_day))
        cumulative_profit: list[float] = list(itertools.accumulate(profit_per_day))

        today = date.today()
        current_ym = (today.year, today.month)

        def _empty_bucket() -> dict[str, int | float]:
            return {"total_units": 0, "total_profit": 0.0, "days_with_data": 0}

        monthly: defaultdict[tuple[int, int], dict[str, int | float]] = defaultdict(_empty_bucket)
        for i, d in enumerate(dates):
            ym = (d.year, d.month)
            if ym == current_ym:
                continue
            bucket = monthly[ym]
            bucket["total_units"] += units_per_day[i]
            bucket["total_profit"] += profit_per_day[i]
            bucket["days_with_data"] += 1

        monthly_rows: list[MonthlyRow] = []
        for ym in sorted(monthly):
            bucket = monthly[ym]
            days_with_data = bucket["days_with_data"]
            total_units = bucket["total_units"]
            total_profit = bucket["total_profit"]
            avg_daily_profit = total_profit / days_with_data if days_with_data else 0.0
            label = datetime(ym[0], ym[1], 1).strftime("%b %Y")
            monthly_rows.append(
                MonthlyRow(
                    label=label,
                    units_str=f"{total_units:,}",
                    profit_str=f"${total_profit:,.2f}",
                    avg_str=f"${avg_daily_profit:,.2f}",
            days_with_data=int(bucket["days_with_data"]),
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
