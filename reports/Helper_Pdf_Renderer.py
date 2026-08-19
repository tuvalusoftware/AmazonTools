"""
Rendering layer for the PDF report pipeline.

Imports BookMetricsData and MonthlyRow from their owning modules.
Helper_Pdf_Renderer is the consumer; it does not own these types.
"""

from __future__ import annotations

import itertools
import textwrap
from typing import Any

import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt

from reports.Helper_Pdf_Metrics import BookMetricsData, MonthlyRow  # noqa: F401 — re-exported

__all__ = ["Helper_Pdf_Renderer", "BookMetricsData", "MonthlyRow"]

FIGSIZE = (9, 7)

_CAPTIONS: dict[str, str] = {
    "daily_units": (
        "Estimated copies sold each day, derived from the daily BSR "
        "(see Methodology on the cover page). Spikes usually track promotions, ads, "
        "or organic ranking improvements."
    ),
    "daily_profit": (
        "Estimated gross royalty profit earned each day. Useful for spotting "
        "high-revenue days and correlating them with marketing activity."
    ),
    "cumulative_units": (
        "Running total of estimated units sold, recomputed from zero over this window "
        "(not the all-time total). A steadily rising slope indicates sustained organic "
        "sales momentum."
    ),
    "cumulative_profit": (
        "Running total of estimated profit, recomputed from zero over this window "
        "(not the all-time total). Use this to track whether the monthly revenue "
        "target is on pace."
    ),
    "monthly_table": (
        "All complete calendar months with data (first-to-first). The current "
        "partial month is excluded — each row spans exactly one full month."
    ),
}


class Helper_Pdf_Renderer:
    """Renders one book's 4-page PDF section (cover, 2 grouped chart pages, table) from pre-computed metrics.

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

    def _save_page(self, fig: Any) -> None:
        self._pdf.savefig(fig)
        plt.close(fig)

    @staticmethod
    def _sparse_labels(
        dates: list, labels: list, step: int = 2, max_ticks: int = 20
    ) -> tuple[list, list]:
        """Subsample to every *step*-th date, widening the step further if that
        would still leave more than *max_ticks* labels (long tracking windows
        would otherwise render hundreds of overlapping x-axis ticks)."""
        if step * max_ticks < len(dates):
            step = -(-len(dates) // max_ticks)  # ceil division
        return dates[::step], labels[::step]

    @staticmethod
    def _add_caption(ax_caption: Any, key: str) -> None:
        ax_caption.axis("off")
        ax_caption.text(
            0.0, 0.5, _CAPTIONS[key],
            transform=ax_caption.transAxes,
            fontsize=7.5, color="#444444", va="center", ha="left",
            wrap=True,
        )

    # ── Cover page ─────────────────────────────────────────────────────────────

    def _render_cover(self, title: str, days: int, price: float, profit_pct: float) -> None:
        fig = plt.figure(figsize=FIGSIZE)
        # Bottom margin so the methodology block (the lowest content, sized
        # dynamically by line-wrapped text) never touches the page edge.
        ax = fig.add_axes((0, 0.05, 1, 0.95))
        ax.axis("off")

        # Cap the title at 3 wrapped lines (long-enough titles are truncated with an
        # ellipsis) so the fixed vertical layout below it never overlaps, regardless
        # of how long the source title string is.
        title_lines = textwrap.wrap(title, width=38) or [title]
        MAX_TITLE_LINES = 3
        if len(title_lines) > MAX_TITLE_LINES:
            title_lines = title_lines[:MAX_TITLE_LINES]
            title_lines[-1] = title_lines[-1].rstrip()[:35].rstrip() + "…"
        wrapped_title = "\n".join(title_lines)

        ax.text(0.5, 0.90, wrapped_title, transform=ax.transAxes,
                 fontsize=20, fontweight="bold", color="#1a3a5c",
                 ha="center", va="top", linespacing=1.3)
        ax.text(0.5, 0.62, "BSR Performance Report", transform=ax.transAxes,
                 fontsize=13, color="#2c5f8a", ha="center", va="top")
        ax.text(0.5, 0.57, f"Rolling {days}-day window", transform=ax.transAxes,
                 fontsize=9.5, color="#666666", ha="center", va="top")

        ax.text(0.08, 0.47, "About this report", transform=ax.transAxes,
                 fontsize=11, fontweight="bold", color="#1a3a5c", va="top")
        about = (
            "This report tracks estimated daily sales and profit for this title, based on its "
            "Amazon Best Sellers Rank (BSR). It covers the trend over the last "
            f"{days} days plus a month-by-month history, so you can spot momentum shifts and "
            "check whether revenue is on pace."
        )
        ax.text(0.08, 0.42, "\n".join(textwrap.wrap(about, width=88)), transform=ax.transAxes,
                 fontsize=9, color="#333333", va="top", linespacing=1.5)

        ax.text(0.08, 0.24, "Methodology", transform=ax.transAxes,
                 fontsize=11, fontweight="bold", color="#1a3a5c", va="top")
        methodology_intro = (
            "BSR is scraped once per day from the Amazon product page. Sales and profit are "
            "estimated with the standard BSR-to-sales power-law approximation:"
        )
        methodology_outro = (
            "Price and royalty % are as entered in the tracker dashboard. These are estimates "
            "only — actual figures reported by Amazon may differ."
        )
        methodology = (
            "\n".join(textwrap.wrap(methodology_intro, width=95)) + "\n\n"
            "    estimated_units  =  round( 10,000 / BSR^0.70 )\n"
            f"    daily_profit     =  estimated_units  ×  ${price:.2f}  ×  {int(profit_pct)}%\n\n"
            + "\n".join(textwrap.wrap(methodology_outro, width=95))
        )
        ax.text(0.08, 0.19, methodology, transform=ax.transAxes,
                 fontsize=8.5, color="#333333", va="top", family="monospace", linespacing=1.6)

        self._save_page(fig)

    # ── Chart pages ────────────────────────────────────────────────────────────

    def _render_chart_pair_page(
        self,
        page_title: str,
        charts: list[tuple[str, str, Any]],
        tick_dates: list,
        tick_labels: list,
    ) -> None:
        """Render two stacked charts (each with a caption strip) on one page.

        Parameters
        ----------
        charts:
            List of ``(caption_key, ylabel, plot_fn)`` tuples, where ``plot_fn(ax)``
            draws the chart onto the given axes.
        """
        fig = plt.figure(figsize=FIGSIZE)
        gs = gridspec.GridSpec(
            4, 1,
            height_ratios=[42, 8, 42, 8],
            hspace=0.55,
            figure=fig,
        )
        gs.update(left=0.10, right=0.97, top=0.93, bottom=0.05)
        fig.suptitle(page_title, fontsize=12, fontweight="bold", y=0.98)

        for i, (caption_key, ylabel, plot_fn) in enumerate(charts):
            ax_chart = fig.add_subplot(gs[i * 2])
            ax_caption = fig.add_subplot(gs[i * 2 + 1])

            plot_fn(ax_chart)
            ax_chart.set_ylabel(ylabel, fontsize=8)
            ax_chart.set_xticks(tick_dates)
            ax_chart.set_xticklabels(tick_labels, rotation=45, ha="right", fontsize=7)
            ax_chart.grid(axis="y", linestyle="--", alpha=0.4)
            self._style_ax(ax_chart)

            self._add_caption(ax_caption, caption_key)

        self._save_page(fig)

    # ── Public rendering method ───────────────────────────────────────────────

    def render_book(self, data: BookMetricsData) -> None:
        """Render one book's section (cover + grouped chart pages + table) into *self._pdf*.

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
        monthly_rows: list[MonthlyRow] = data["monthly_rows"]

        # Derive representative price from the latest snapshot with a non-zero price
        latest_price = 0.0
        for row in reversed(data["snapshot_rows"]):
            if row.get("price"):
                latest_price = float(row["price"])
                break

        # Both chart pages become unreadable once the tracking window runs into
        # the hundreds of days (daily bars too thin to see; cumulative totals
        # dominated by early history) — cap both to the most recent stretch.
        # The cumulative totals are recomputed from zero over that window
        # (older days are ignored entirely, not just clipped off the plot).
        DAILY_CHART_WINDOW_DAYS = 30
        windowed = len(dates) > DAILY_CHART_WINDOW_DAYS
        daily_dates = dates[-DAILY_CHART_WINDOW_DAYS:]
        daily_units = units_per_day[-DAILY_CHART_WINDOW_DAYS:]
        daily_profit = profit_per_day[-DAILY_CHART_WINDOW_DAYS:]
        daily_tick_dates, daily_tick_labels = self._sparse_labels(
            daily_dates, date_labels[-DAILY_CHART_WINDOW_DAYS:], step=2
        )
        daily_page_title = (
            "Daily Sales & Profit"
            if not windowed
            else f"Daily Sales & Profit (Last {DAILY_CHART_WINDOW_DAYS} Days)"
        )
        windowed_cumulative_units = list(itertools.accumulate(daily_units))
        windowed_cumulative_profit = list(itertools.accumulate(daily_profit))
        cumulative_page_title = (
            "Cumulative Sales & Profit"
            if not windowed
            else f"Cumulative Sales & Profit (Last {DAILY_CHART_WINDOW_DAYS} Days)"
        )

        # Chart/table page headers are a single suptitle line (unlike the cover,
        # which wraps the title over up to 3 lines) — long titles must be
        # truncated here or they overflow past the page width.
        MAX_HEADER_TITLE_LEN = 40
        short_title = title if len(title) <= MAX_HEADER_TITLE_LEN else (
            title[: MAX_HEADER_TITLE_LEN - 1].rstrip() + "…"
        )

        def _prefix(chart_title: str) -> str:
            return f"[{short_title}] — {chart_title}"

        self._render_cover(title, days=len(dates), price=latest_price, profit_pct=price_pct)

        # Page — Daily Units Sold + Daily Profit
        self._render_chart_pair_page(
            _prefix(daily_page_title),
            charts=[
                (
                    "daily_units", "Estimated Units Sold",
                    lambda ax: ax.bar(daily_dates, daily_units, color="#4a90d9"),
                ),
                (
                    "daily_profit", "Profit (USD)",
                    lambda ax: ax.bar(daily_dates, daily_profit, color="#e07b39"),
                ),
            ],
            tick_dates=daily_tick_dates,
            tick_labels=daily_tick_labels,
        )

        # Page — Cumulative Units + Cumulative Profit
        self._render_chart_pair_page(
            _prefix(cumulative_page_title),
            charts=[
                (
                    "cumulative_units", "Total Units Sold",
                    lambda ax: (
                        ax.plot(daily_dates, windowed_cumulative_units, marker="o", markersize=3,
                                color="#4a90d9", linewidth=1.4),
                        ax.fill_between(daily_dates, windowed_cumulative_units, alpha=0.12, color="#4a90d9"),
                    ),
                ),
                (
                    "cumulative_profit", "Total Profit (USD)",
                    lambda ax: (
                        ax.plot(daily_dates, windowed_cumulative_profit, marker="o", markersize=3,
                                color="green", linewidth=1.4),
                        ax.fill_between(daily_dates, windowed_cumulative_profit, alpha=0.12, color="green"),
                    ),
                ),
            ],
            tick_dates=daily_tick_dates,
            tick_labels=daily_tick_labels,
        )

        # Page — Monthly Profit Summary
        col_headers = ["Month", "Est. Units Sold", "Total Profit", "Avg Daily Profit", "Days"]
        fig = plt.figure(figsize=FIGSIZE)
        gs = gridspec.GridSpec(2, 1, height_ratios=[85, 15], hspace=0.12, figure=fig)
        gs.update(left=0.04, right=0.97, top=0.93, bottom=0.05)
        ax_tbl = fig.add_subplot(gs[0])
        ax_caption = fig.add_subplot(gs[1])
        fig.suptitle(_prefix("Monthly Profit Summary"), fontsize=12, fontweight="bold", y=0.98)

        ax_tbl.axis("off")

        if monthly_rows:
            cell_text = [
                [r.label, r.units_str, r.profit_str, r.avg_str, str(r.days_with_data)]
                for r in monthly_rows
            ]
        else:
            cell_text = [["No monthly data yet", "—", "—", "—", "—"]]

        # Size the table bbox to the row count instead of a fixed height —
        # a fixed height made a single-month table absurdly tall and a
        # many-month table cramped. Each row gets ~0.075 of the axes height,
        # clamped so it never disappears (few rows) or overflows (many rows).
        row_count = len(cell_text) + 1
        table_top = 0.90
        target_row_height = 0.075
        min_table_height = 2 * target_row_height
        max_table_height = table_top - 0.05
        table_height = max(min_table_height, min(row_count * target_row_height, max_table_height))
        tbl = ax_tbl.table(
            cellText=cell_text,
            colLabels=col_headers,
            cellLoc="center",
            bbox=[0.02, table_top - table_height, 0.96, table_height],
        )
        # Scale font to match the actual per-row height (which is compressed
        # once row_count pushes past max_table_height) so text never overlaps.
        actual_row_height = table_height / row_count
        fontsize = max(8, min(14, 14 * actual_row_height / target_row_height))
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(fontsize)
        tbl.auto_set_column_width(list(range(len(col_headers))))
        # auto_set_column_width sizes "Days" too tightly for its header text
        # (it only measures the short numeric cell values) — widen it and
        # shrink the other columns proportionally so the row width is unchanged.
        days_col = len(col_headers) - 1
        old_widths = [tbl[0, col].get_width() for col in range(len(col_headers))]
        total_width = sum(old_widths)
        new_days_width = old_widths[days_col] * 1.8
        shrink_factor = (total_width - new_days_width) / (total_width - old_widths[days_col])
        new_widths = [
            new_days_width if col == days_col else old_widths[col] * shrink_factor
            for col in range(len(col_headers))
        ]
        for row_idx in range(len(cell_text) + 1):
            for col in range(len(col_headers)):
                tbl[row_idx, col].set_width(new_widths[col])
        for col in range(len(col_headers)):
            tbl[0, col].set_facecolor("#2c5f8a")
            tbl[0, col].set_text_props(color="white", fontweight="bold")
        for row_idx in range(1, len(cell_text) + 1):
            bg = "#e8f0f7" if row_idx % 2 == 0 else "white"
            for col in range(len(col_headers)):
                tbl[row_idx, col].set_facecolor(bg)

        self._add_caption(ax_caption, "monthly_table")
        self._save_page(fig)
