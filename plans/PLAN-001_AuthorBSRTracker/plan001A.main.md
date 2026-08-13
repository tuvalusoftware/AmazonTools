# PLAN-001A: Mock PDF Sales & Profit Chart Report

A standalone script that generates a single-page PDF containing four sequential charts derived from fully mocked BSR/sales data — intended as a visual prototype before the real `bsr_snapshots` pipeline is wired up.

---

## Ownership

Python-only script inside `amazon-review-scraper`.  
Output: one PDF file (`reports/mock_charts.pdf`).  
No database, no SMTP, no web server required.

---

## Scope

| Module | Description |
|---|---|
| `reports/mock_charts.py` | Entry-point script — generates mock data and renders the PDF |
| `reports/` | Output folder — PDF written here |
| `requirements.txt` | Add `matplotlib` if not already present |

---

## Current behavior (baseline)

- No reporting or charting capability exists in the repo.
- `bsr_snapshots` data is scraped but never visualised.
- No PDF output of any kind exists.

---

## Problems / gaps

1. No way to preview what daily sales / profit charts would look like before live data arrives.
2. Stakeholders need a concrete visual mock to sign off on chart layout before building the real pipeline.

---

## Target outcomes

| Theme | Intent |
|---|---|
| Mock data generation | Produce 30 days of plausible daily sales counts and profit values in memory — no DB needed |
| Four sequential charts | Render all four panels onto a single multi-page PDF in the prescribed order |
| Chart 1 — Daily units sold | Bar or line chart; X = date, Y = units sold per day |
| Chart 2 — Daily profit | Bar or line chart; X = date, Y = profit (USD) per day |
| Chart 3 — Cumulative units sold | Line chart; X = date, Y = running total of units sold |
| Chart 4 — Cumulative profit | Line chart; X = date, Y = running total of profit (USD) |
| Single-file output | All four charts written sequentially to `reports/mock_charts.pdf` |
| Zero external dependencies beyond matplotlib | Only `matplotlib` (+ `numpy` for convenience) added to `requirements.txt` |

---

## Suggested layout

```
amazon-review-scraper/
├── reports/
│   ├── mock_charts.py        # new — mock data + PDF generation script
│   └── mock_charts.pdf       # generated output (git-ignored)
└── requirements.txt          # add matplotlib (+ numpy if needed)
```

---

## Implementation notes

- **Mock data** — generate 30 daily entries spanning the last 30 days from `datetime.today()`. Use `random.seed(42)` for reproducibility. Units sold per day: random integer 50–300. Unit price fixed at `$14.99`, profit per unit = `price × profit_pct` (use 70 % as default). Daily profit = `units_sold × profit_per_unit`.
- **Cumulative series** — compute with `itertools.accumulate` or a simple running sum; no `numpy` required (but allowed).
- **PDF backend** — use `matplotlib.backends.backend_pdf.PdfPages`. Call `savefig` once per chart; `PdfPages` writes each as a new PDF page.
- **Chart order** — page 1: daily units sold, page 2: daily profit, page 3: cumulative units sold, page 4: cumulative profit.
- **Styling** — minimal: title, X/Y axis labels, grid lines. Use a single shared colour per series. No legend needed when only one series per chart.
- **Running the script** — `python reports/mock_charts.py`; the PDF is created at `reports/mock_charts.pdf` relative to repo root. The script resolves the output path from `__file__` so it works regardless of `cwd`.
- **No new config** — hard-code all mock parameters (`DAYS = 30`, `PRICE = 14.99`, `PROFIT_PCT = 0.70`, `SEED = 42`) as module-level constants at the top of the script.

---

## Chapters

| Chapter | File | Focus | Status |
|---|---|---|---|
| C001 | `plan001A.C001_MockPdfCharts.todo.md` | Mock data generation + four-chart PDF script | Not started |

---

## Files in this plan folder

| File | Purpose |
|---|---|
| `plan001A.main.md` | This overview |
| `plan001A.C001_MockPdfCharts.todo.md` | Chapter 1 tasks — mock data + PDF generation |

---

## Done when

- [ ] `python reports/mock_charts.py` runs without errors from repo root.
- [ ] `reports/mock_charts.pdf` is created and contains exactly four pages.
- [ ] Page 1 shows a labelled daily units-sold chart (30 data points).
- [ ] Page 2 shows a labelled daily profit chart (30 data points).
- [ ] Page 3 shows a labelled cumulative units-sold chart (running total).
- [ ] Page 4 shows a labelled cumulative profit chart (running total).
- [ ] All charts use the same mock dataset (same seed, same date range).
- [ ] `matplotlib` is listed in `requirements.txt`.
