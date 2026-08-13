# PLAN-001A — C001: Mock PDF Chart Script

← [`plan001A.main.md`](plan001A.main.md)

Delivers a runnable `reports/mock_charts.py` that generates 30 days of mock sales/profit data and writes a four-page PDF to `reports/mock_charts.pdf`.

---

## Setup

- [x] Create `reports/` folder at repo root (add `reports/.gitkeep`; the generated PDF will be git-ignored)
- [x] Add `reports/mock_charts.pdf` to `.gitignore`
- [x] Add `matplotlib` to `requirements.txt` (check if already present first)
- [x] Optionally add `numpy` to `requirements.txt` if used for accumulation (not required)

---

## Mock data generation (`reports/mock_charts.py`)

- [x] Add module-level constants at the top of the file:
  ```
  DAYS = 30
  PRICE = 14.99
  PROFIT_PCT = 0.70
  SEED = 42
  OUTPUT_PATH = Path(__file__).parent / "mock_charts.pdf"
  ```
- [x] Build `dates` list: `[today - timedelta(days=i) for i in range(DAYS-1, -1, -1)]`
- [x] Set `random.seed(SEED)` before generating any random values
- [x] Build `units_per_day`: list of `random.randint(50, 300)` for each date (length = `DAYS`)
- [x] Compute `profit_per_day`: `[u * PRICE * PROFIT_PCT for u in units_per_day]`
- [x] Compute `cumulative_units`: running sum of `units_per_day` (use `itertools.accumulate`)
- [x] Compute `cumulative_profit`: running sum of `profit_per_day` (use `itertools.accumulate`)
- [x] Format date labels as `"Aug 01"` strings for X-axis tick labels

---

## Chart rendering

- [x] Open `PdfPages(OUTPUT_PATH)` as a context manager
- [x] Define a shared helper `save_chart(fig, pdf)` that calls `pdf.savefig(fig)` then `plt.close(fig)` — avoids resource leaks
- [x] **Chart 1 — Daily units sold** (page 1):
  - [x] `plt.bar(dates, units_per_day)` or `plt.plot`
  - [x] Title: `"Daily Units Sold"`
  - [x] X-label: `"Date"`, Y-label: `"Units Sold"`
  - [x] X-tick rotation: 45°
  - [x] Grid: `plt.grid(axis='y', linestyle='--', alpha=0.5)`
  - [x] Call `save_chart(fig, pdf)`
- [x] **Chart 2 — Daily profit** (page 2):
  - [x] `plt.bar(dates, profit_per_day)` or `plt.plot`
  - [x] Title: `"Daily Profit (USD)"`
  - [x] X-label: `"Date"`, Y-label: `"Profit (USD)"`
  - [x] X-tick rotation: 45°
  - [x] Grid: `plt.grid(axis='y', linestyle='--', alpha=0.5)`
  - [x] Call `save_chart(fig, pdf)`
- [x] **Chart 3 — Cumulative units sold** (page 3):
  - [x] `plt.plot(dates, cumulative_units, marker='o', markersize=3)`
  - [x] Title: `"Cumulative Units Sold"`
  - [x] X-label: `"Date"`, Y-label: `"Total Units Sold"`
  - [x] X-tick rotation: 45°
  - [x] Grid: `plt.grid(linestyle='--', alpha=0.5)`
  - [x] Call `save_chart(fig, pdf)`
- [x] **Chart 4 — Cumulative profit** (page 4):
  - [x] `plt.plot(dates, cumulative_profit, marker='o', markersize=3, color='green')`
  - [x] Title: `"Cumulative Profit (USD)"`
  - [x] X-label: `"Date"`, Y-label: `"Total Profit (USD)"`
  - [x] X-tick rotation: 45°
  - [x] Grid: `plt.grid(linestyle='--', alpha=0.5)`
  - [x] Call `save_chart(fig, pdf)`
- [x] Use `plt.tight_layout()` on each figure before saving to prevent label clipping

---

## Output & metadata

- [x] After the `PdfPages` context manager closes, print: `f"PDF written to {OUTPUT_PATH}"`
- [x] Add a `if __name__ == "__main__":` guard around the generation call

---

## Verification

- [x] Run `pip install matplotlib` (or `pip install -r requirements.txt`) in a fresh environment
- [x] Run `python reports/mock_charts.py` from repo root — exits with code 0
- [x] Confirm `reports/mock_charts.pdf` exists
- [x] Open PDF and verify:
  - [x] Exactly 4 pages
  - [x] Page 1 title = "Daily Units Sold", bar chart with 30 bars
  - [x] Page 2 title = "Daily Profit (USD)", bar chart with 30 bars
  - [x] Page 3 title = "Cumulative Units Sold", line chart rising monotonically
  - [x] Page 4 title = "Cumulative Profit (USD)", line chart rising monotonically, green line
  - [x] X-axis labels are date strings (e.g. "Aug 01")
  - [x] Running the script twice produces an identical PDF (seed is fixed)
