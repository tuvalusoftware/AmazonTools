import itertools
import random
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.backends.backend_pdf import PdfPages

# ── User-configured parameters ────────────────────────────────────────────────
PRICE = 14.99        # book list price (USD)
PROFIT_PCT = 0.70    # royalty rate entered by user

# ── Report window ──────────────────────────────────────────────────────────────
DAYS = 30
MONTHLY_MONTHS = 6   # how many months back the monthly table covers

FIGSIZE = (9, 7)
CHART_HEIGHT_RATIO = [62, 38]
OUTPUT_PATH = Path(__file__).parent / "book_performance_report.pdf"

# ── Internal seed (reproducible placeholder data) ─────────────────────────────
_SEED = 42

DESCRIPTIONS = {
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
    "daily_profit": (
        "What it shows",
        "Estimated gross royalty profit earned each day, derived from the daily BSR.\n"
        "Useful for identifying high-revenue days and correlating them with marketing activity.",
        "Data source & formula",
        "estimated_units  =  round( 10,000 / BSR^0.70 )\n"
        "                    (standard Amazon BSR-to-sales power-law approximation)\n"
        f"daily_profit      =  estimated_units  ×  ${PRICE:.2f}  ×  {int(PROFIT_PCT*100)}%\n"
        "Price and royalty % are entered by the user in the tracker dashboard.",
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
        f"Aggregated estimated profit and unit figures grouped by calendar month,\n"
        f"covering the past {MONTHLY_MONTHS} months up to today.\n"
        f"The current (partial) month reflects only the days elapsed so far.",
        "Data source & formula",
        "BSR scraped daily  →  estimated_units  →  profit per day  →  summed by month\n"
        "Avg Daily Profit  =  Total Monthly Profit  ÷  days with data in that month\n"
        f"Price: ${PRICE:.2f}  |  Royalty: {int(PROFIT_PCT*100)}%  (user-configured)",
    ),
}


# ── Data builders ──────────────────────────────────────────────────────────────

def _bsr_to_units(bsr: float) -> int:
    """Approximate daily units from BSR using a power-law conversion."""
    return max(1, round(10_000 / (bsr ** 0.70)))


def _build_daily_data():
    today = date.today()
    dates = [today - timedelta(days=i) for i in range(DAYS - 1, -1, -1)]
    random.seed(_SEED)
    base_bsr = 12_000
    bsr_per_day = []
    for i in range(DAYS):
        noise = random.randint(-1_500, 2_000)
        trend = -int(i * 120)
        bsr_per_day.append(max(500, base_bsr + trend + noise))

    units_per_day = [_bsr_to_units(b) for b in bsr_per_day]
    profit_per_day = [u * PRICE * PROFIT_PCT for u in units_per_day]
    cumulative_units = list(itertools.accumulate(units_per_day))
    cumulative_profit = list(itertools.accumulate(profit_per_day))

    date_labels = [d.strftime("%b %d") for d in dates]
    return dates, date_labels, units_per_day, cumulative_units, profit_per_day, cumulative_profit


def _build_monthly_data():
    today = date.today()
    month = today.month - MONTHLY_MONTHS
    year = today.year + (month - 1) // 12
    month = ((month - 1) % 12) + 1
    start = date(year, month, 1)

    total_days = (today - start).days + 1
    random.seed(_SEED + 1)
    all_dates = [start + timedelta(days=i) for i in range(total_days)]
    all_bsr = [max(500, random.randint(4_000, 18_000)) for _ in all_dates]
    all_units = [_bsr_to_units(b) for b in all_bsr]
    all_profits = [u * PRICE * PROFIT_PCT for u in all_units]

    bucket_profit: dict = defaultdict(float)
    bucket_units: dict = defaultdict(int)
    bucket_days: dict = defaultdict(int)
    for d, u, p in zip(all_dates, all_units, all_profits):
        key = (d.year, d.month)
        bucket_profit[key] += p
        bucket_units[key] += u
        bucket_days[key] += 1

    rows = []
    for key in sorted(bucket_profit):
        yr, mo = key
        label = date(yr, mo, 1).strftime("%B %Y")
        total_p = bucket_profit[key]
        days = bucket_days[key]
        avg_p = total_p / days
        total_u = bucket_units[key]
        rows.append((label, f"{total_u:,}", f"${total_p:,.2f}", f"${avg_p:,.2f}", days))
    return rows


# ── Rendering helpers ──────────────────────────────────────────────────────────

def _sparse_labels(dates, labels, step=2):
    return dates[::step], labels[::step]


def _style_ax(ax):
    ax.tick_params(axis="both", labelsize=7)
    ax.set_xlabel("Date", fontsize=8)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)


def _add_description(ax_desc, key):
    what_head, what_body, how_head, how_body = DESCRIPTIONS[key]
    ax_desc.axis("off")
    ax_desc.set_facecolor("#f5f7fa")

    x = 0.02
    y = 0.95

    # Each line of text occupies roughly 0.13 axes-units at fontsize 8 with linespacing 1.4
    LINE_H = 0.13
    HEAD_GAP = 0.14  # gap between a heading and its body text

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


def _new_page(title, height_ratios=None):
    fig = plt.figure(figsize=FIGSIZE)
    gs = gridspec.GridSpec(2, 1,
                           height_ratios=height_ratios or CHART_HEIGHT_RATIO,
                           hspace=0.30, figure=fig)
    gs.update(left=0.10, right=0.97, top=0.93, bottom=0.04)
    ax_chart = fig.add_subplot(gs[0])
    ax_desc = fig.add_subplot(gs[1])
    fig.suptitle(title, fontsize=12, fontweight="bold", y=0.98)
    return fig, ax_chart, ax_desc


def save_page(fig, pdf):
    pdf.savefig(fig)
    plt.close(fig)


# ── Main ───────────────────────────────────────────────────────────────────────

def generate_pdf():
    dates, date_labels, units_per_day, cumulative_units, profit_per_day, cumulative_profit = _build_daily_data()
    tick_dates, tick_labels = _sparse_labels(dates, date_labels)

    with PdfPages(OUTPUT_PATH) as pdf:

        # Page 1 — Estimated books sold per day
        fig, ax, ax_desc = _new_page("Estimated Books Sold per Day")
        ax.bar(dates, units_per_day, color="#4a90d9")
        ax.set_ylabel("Estimated Units Sold", fontsize=8)
        ax.set_xticks(tick_dates)
        ax.set_xticklabels(tick_labels, rotation=45, ha="right", fontsize=7)
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        _style_ax(ax)
        _add_description(ax_desc, "daily_units")
        save_page(fig, pdf)

        # Page 2 — Daily profit
        fig, ax, ax_desc = _new_page("Estimated Daily Profit (USD)")
        ax.bar(dates, profit_per_day, color="#e07b39")
        ax.set_ylabel("Profit (USD)", fontsize=8)
        ax.set_xticks(tick_dates)
        ax.set_xticklabels(tick_labels, rotation=45, ha="right", fontsize=7)
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        _style_ax(ax)
        _add_description(ax_desc, "daily_profit")
        save_page(fig, pdf)

        # Page 3 — Cumulative profit
        fig, ax, ax_desc = _new_page("Cumulative Estimated Profit (USD)")
        ax.plot(dates, cumulative_profit, marker="o", markersize=3, color="green", linewidth=1.4)
        ax.fill_between(dates, cumulative_profit, alpha=0.12, color="green")
        ax.set_ylabel("Total Profit (USD)", fontsize=8)
        ax.set_xticks(tick_dates)
        ax.set_xticklabels(tick_labels, rotation=45, ha="right", fontsize=7)
        ax.grid(linestyle="--", alpha=0.4)
        _style_ax(ax)
        _add_description(ax_desc, "cumulative_profit")
        save_page(fig, pdf)

        # Page 4 — Cumulative books sold
        fig, ax, ax_desc = _new_page("Cumulative Estimated Books Sold")
        ax.plot(dates, cumulative_units, marker="o", markersize=3, color="#4a90d9", linewidth=1.4)
        ax.fill_between(dates, cumulative_units, alpha=0.12, color="#4a90d9")
        ax.set_ylabel("Total Units Sold", fontsize=8)
        ax.set_xticks(tick_dates)
        ax.set_xticklabels(tick_labels, rotation=45, ha="right", fontsize=7)
        ax.grid(linestyle="--", alpha=0.4)
        _style_ax(ax)
        _add_description(ax_desc, "cumulative_units")
        save_page(fig, pdf)

        # Page 5 — Monthly profit table
        monthly_rows = _build_monthly_data()
        col_headers = ["Month", "Est. Units Sold", "Total Profit", "Avg Daily Profit", "Days"]
        fig = plt.figure(figsize=FIGSIZE)
        gs = gridspec.GridSpec(2, 1, height_ratios=[58, 42], hspace=0.08, figure=fig)
        gs.update(left=0.04, right=0.97, top=0.93, bottom=0.04)
        ax_tbl = fig.add_subplot(gs[0])
        ax_desc = fig.add_subplot(gs[1])
        fig.suptitle("Monthly Profit Summary", fontsize=12, fontweight="bold", y=0.98)

        ax_tbl.axis("off")
        tbl = ax_tbl.table(
            cellText=[[r[0], r[1], r[2], r[3], str(r[4])] for r in monthly_rows],
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
        for row_idx, _ in enumerate(monthly_rows, start=1):
            bg = "#e8f0f7" if row_idx % 2 == 0 else "white"
            for col in range(len(col_headers)):
                tbl[row_idx, col].set_facecolor(bg)

        _add_description(ax_desc, "monthly_table")
        save_page(fig, pdf)

    print(f"PDF written to {OUTPUT_PATH}")


if __name__ == "__main__":
    generate_pdf()
