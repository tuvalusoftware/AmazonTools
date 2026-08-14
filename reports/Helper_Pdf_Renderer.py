"""
Rendering layer for the PDF report pipeline.

Imports BookMetricsData and MonthlyRow from their owning modules.
Helper_Pdf_Renderer is the consumer; it does not own these types.
"""

from __future__ import annotations

from typing import Any

import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt

from reports.Helper_Pdf_Metrics import BookMetricsData, MonthlyRow  # noqa: F401 — re-exported

__all__ = ["Helper_Pdf_Renderer", "BookMetricsData", "MonthlyRow"]

FIGSIZE = (9, 7)
CHART_HEIGHT_RATIO = [62, 38]

_DESCRIPTIONS_STATIC: dict[str, tuple[str, str, str, str]] = {
    "daily_units": (
        "What it shows",
        "Estimated number of copies sold each day over the past 30 days.\n"
        "Each bar represents a single calendar day.\n"
        "Spikes typically correspond to promotions, ads, or organic ranking improvements.",
        "Data source & formula",
        "estimated_units  =  round( 10,000 / BSR^0.70 )\n"
        "                    (standard Amazon BSR-to-sales power-law approximation)\n"
        "BSR is scraped daily from the Amazon product page.",
    ),
    "cumulative_units": (
        "What it shows",
        "Running total of estimated copies sold from day 1 through the current day.\n"
        "A steadily rising slope indicates sustained organic sales momentum.\n"
        "Flattening segments mark low-BSR (high-rank) days with few sales.",
        "Data source & formula",
        "cumulative_units[i]  =  Σ  estimated_units[0 … i]\n"
        "estimated_units[j]   =  round( 10,000 / BSR[j]^0.70 )",
    ),
    "cumulative_profit": (
        "What it shows",
        "Running total of estimated profit accumulated day by day over the 30-day window.\n"
        "Use this to track whether the monthly revenue target is on pace.",
        "Data source & formula",
        "cumulative_profit[i]  =  Σ  daily_profit[0 … i]\n"
        "                       =  Σ  ( estimated_units[j] × price × royalty_pct )  for j in 0…i",
    ),
    "monthly_table": (
        "What it shows",
        "All complete calendar months with data (first-to-first).\n"
        "The current partial month is excluded — each row spans exactly one full month.",
        "Data source & formula",
        "BSR scraped daily  →  estimated_units  →  profit per day  →  summed by month\n"
        "Avg Daily Profit  =  Total Monthly Profit  ÷  days with data in that month",
    ),
}


def _build_daily_profit_description(price: float, profit_pct: float) -> tuple[str, str, str, str]:
    return (
        "What it shows",
        "Estimated gross royalty profit earned each day, derived from the daily BSR.\n"
        "Useful for identifying high-revenue days and correlating them with marketing activity.",
        "Data source & formula",
        "estimated_units  =  round( 10,000 / BSR^0.70 )\n"
        "                    (standard Amazon BSR-to-sales power-law approximation)\n"
        f"daily_profit      =  estimated_units  ×  ${price:.2f}  ×  {int(profit_pct * 100)}%\n"
        "Price and royalty % are entered by the user in the tracker dashboard.",
    )


class Helper_Pdf_Renderer:
    """Renders one book's 5-page PDF section from pre-computed metrics.

    Parameters
    ----------
    pdf:
        An open ``matplotlib.backends.backend_pdf.PdfPages`` context into
        which pages are saved.
    """

    def __init__(self, pdf: Any) -> None:
        self._pdf = pdf

    # ── Private static helpers ────────────────────────────────────────────────

    @staticmethod
    def _style_ax(ax: Any) -> None:
        ax.tick_params(axis="both", labelsize=7)
        ax.set_xlabel("Date", fontsize=8)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)

    @staticmethod
    def _new_page(title: str, height_ratios: list[int] | None = None) -> tuple[Any, Any, Any]:
        fig = plt.figure(figsize=FIGSIZE)
        gs = gridspec.GridSpec(
            2, 1,
            height_ratios=height_ratios or CHART_HEIGHT_RATIO,
            hspace=0.30,
            figure=fig,
        )
        gs.update(left=0.10, right=0.97, top=0.93, bottom=0.04)
        ax_chart = fig.add_subplot(gs[0])
        ax_desc = fig.add_subplot(gs[1])
        fig.suptitle(title, fontsize=12, fontweight="bold", y=0.98)
        return fig, ax_chart, ax_desc

    def _save_page(self, fig: Any) -> None:
        self._pdf.savefig(fig)
        plt.close(fig)

    @staticmethod
    def _sparse_labels(dates: list, labels: list, step: int = 2) -> tuple[list, list]:
        return dates[::step], labels[::step]

    @staticmethod
    def _add_description(
        ax_desc: Any,
        key: str,
        price: float = 0.0,
        profit_pct: float = 0.70,
    ) -> None:
        if key == "daily_profit":
            what_head, what_body, how_head, how_body = _build_daily_profit_description(price, profit_pct)
        else:
            what_head, what_body, how_head, how_body = _DESCRIPTIONS_STATIC[key]

        ax_desc.axis("off")
        ax_desc.set_facecolor("#f5f7fa")

        x = 0.02
        y = 0.95

        LINE_H = 0.13
        HEAD_GAP = 0.14

        ax_desc.text(x, y, what_head, transform=ax_desc.transAxes,
                     fontsize=8.5, fontweight="bold", color="#1a3a5c", va="top")
        y -= HEAD_GAP
        ax_desc.text(x, y, what_body, transform=ax_desc.transAxes,
                     fontsize=8, color="#333333", va="top", linespacing=1.4)
        y -= LINE_H * (what_body.count("\n") + 1) + 0.03

        ax_desc.text(x, y, how_head, transform=ax_desc.transAxes,
                     fontsize=8.5, fontweight="bold", color="#1a3a5c", va="top")
        y -= HEAD_GAP
        ax_desc.text(x, y, how_body, transform=ax_desc.transAxes,
                     fontsize=8, color="#333333", va="top", family="monospace", linespacing=1.4)

    # ── Public rendering method ───────────────────────────────────────────────

    def render_book(self, data: BookMetricsData) -> None:
        """Render all 5 pages for a single book into *self._pdf*.

        Parameters
        ----------
        data:
            Fully-computed metrics dict produced by ``Helper_Pdf_Metrics.compute()``.
        """
        title = data["title"]
        price_pct = data["profit_pct"]
        dates = data["dates"]
        date_labels = data["date_labels"]
        units_per_day = data["units_per_day"]
        profit_per_day = data["profit_per_day"]
        cumulative_units = data["cumulative_units"]
        cumulative_profit = data["cumulative_profit"]
        monthly_rows: list[MonthlyRow] = data["monthly_rows"]

        # Derive representative price from the latest snapshot with a non-zero price
        latest_price = 0.0
        for row in reversed(data["snapshot_rows"]):
            if row.get("price"):
                latest_price = float(row["price"])
                break

        tick_dates, tick_labels = self._sparse_labels(dates, date_labels, step=2)

        def _prefix(chart_title: str) -> str:
            return f"[{title}] — {chart_title}"

        # Page 1 — Estimated Books Sold per Day
        fig, ax, ax_desc = self._new_page(_prefix("Estimated Books Sold per Day"))
        ax.bar(dates, units_per_day, color="#4a90d9")
        ax.set_ylabel("Estimated Units Sold", fontsize=8)
        ax.set_xticks(tick_dates)
        ax.set_xticklabels(tick_labels, rotation=45, ha="right", fontsize=7)
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        self._style_ax(ax)
        self._add_description(ax_desc, "daily_units", price=latest_price, profit_pct=price_pct)
        self._save_page(fig)

        # Page 2 — Estimated Daily Profit
        fig, ax, ax_desc = self._new_page(_prefix("Estimated Daily Profit (USD)"))
        ax.bar(dates, profit_per_day, color="#e07b39")
        ax.set_ylabel("Profit (USD)", fontsize=8)
        ax.set_xticks(tick_dates)
        ax.set_xticklabels(tick_labels, rotation=45, ha="right", fontsize=7)
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        self._style_ax(ax)
        self._add_description(ax_desc, "daily_profit", price=latest_price, profit_pct=price_pct)
        self._save_page(fig)

        # Page 3 — Cumulative Estimated Profit
        fig, ax, ax_desc = self._new_page(_prefix("Cumulative Estimated Profit (USD)"))
        ax.plot(dates, cumulative_profit, marker="o", markersize=3, color="green", linewidth=1.4)
        ax.fill_between(dates, cumulative_profit, alpha=0.12, color="green")
        ax.set_ylabel("Total Profit (USD)", fontsize=8)
        ax.set_xticks(tick_dates)
        ax.set_xticklabels(tick_labels, rotation=45, ha="right", fontsize=7)
        ax.grid(linestyle="--", alpha=0.4)
        self._style_ax(ax)
        self._add_description(ax_desc, "cumulative_profit", price=latest_price, profit_pct=price_pct)
        self._save_page(fig)

        # Page 4 — Cumulative Estimated Books Sold
        fig, ax, ax_desc = self._new_page(_prefix("Cumulative Estimated Books Sold"))
        ax.plot(dates, cumulative_units, marker="o", markersize=3, color="#4a90d9", linewidth=1.4)
        ax.fill_between(dates, cumulative_units, alpha=0.12, color="#4a90d9")
        ax.set_ylabel("Total Units Sold", fontsize=8)
        ax.set_xticks(tick_dates)
        ax.set_xticklabels(tick_labels, rotation=45, ha="right", fontsize=7)
        ax.grid(linestyle="--", alpha=0.4)
        self._style_ax(ax)
        self._add_description(ax_desc, "cumulative_units", price=latest_price, profit_pct=price_pct)
        self._save_page(fig)

        # Page 5 — Monthly Profit Summary
        col_headers = ["Month", "Est. Units Sold", "Total Profit", "Avg Daily Profit", "Days"]
        fig = plt.figure(figsize=FIGSIZE)
        gs = gridspec.GridSpec(2, 1, height_ratios=[58, 42], hspace=0.08, figure=fig)
        gs.update(left=0.04, right=0.97, top=0.93, bottom=0.04)
        ax_tbl = fig.add_subplot(gs[0])
        ax_desc = fig.add_subplot(gs[1])
        fig.suptitle(_prefix("Monthly Profit Summary"), fontsize=12, fontweight="bold", y=0.98)

        ax_tbl.axis("off")

        if monthly_rows:
            cell_text = [
                [r.label, r.units_str, r.profit_str, r.avg_str, str(r.days_with_data)]
                for r in monthly_rows
            ]
        else:
            cell_text = [["No monthly data yet", "—", "—", "—", "—"]]

        tbl = ax_tbl.table(
            cellText=cell_text,
            colLabels=col_headers,
            cellLoc="center",
            loc="center",
        )
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(9)
        tbl.auto_set_column_width(list(range(len(col_headers))))
        for col in range(len(col_headers)):
            tbl[0, col].set_facecolor("#2c5f8a")
            tbl[0, col].set_text_props(color="white", fontweight="bold")
        for row_idx in range(1, len(cell_text) + 1):
            bg = "#e8f0f7" if row_idx % 2 == 0 else "white"
            for col in range(len(col_headers)):
                tbl[row_idx, col].set_facecolor(bg)

        self._add_description(ax_desc, "monthly_table", price=latest_price, profit_pct=price_pct)
        self._save_page(fig)
