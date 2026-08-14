# PLAN-001 — C006A: Type Definitions for PDF Report Pipeline

← [plan001.main.md](plan001.main.md)

Each type is defined in the module that produces it.
Downstream modules import from the owning module — no central `_types.py` file.

**Depends on:** none — must be implemented before [plan001.C006_PdfReportFromDb.todo.md](plan001.C006_PdfReportFromDb.todo.md)

---

## `utils/Repo_Snapshot.py` — `DailySnapshotRow` + `SnapshotRepo`

New dedicated file for snapshot data. `load_daily_snapshots()` moves here from `BookRepo`.
`DailySnapshotRow` is owned here because `SnapshotRepo` is the producer.

- [x] Create `utils/Repo_Snapshot.py`
- [x] Add:
  ```python
  from __future__ import annotations
  from typing import TypedDict
  from utils.registry import _get_db_path   # reuse shared db path helper

  class DailySnapshotRow(TypedDict):
      date: str       # ISO date string "2026-08-01"
      rank: int       # best (lowest) rank seen that day
      price: float    # highest price seen that day; 0.0 when unavailable

  class SnapshotRepo:
      def load_daily_snapshots(self, asin: str, days: int = 90) -> list[DailySnapshotRow]:
          ...
  ```
- [x] Move `load_daily_snapshots()` logic from `BookRepo` into `SnapshotRepo.load_daily_snapshots()`
- [x] Remove `load_daily_snapshots()` from `BookRepo` in `utils/registry.py`
- [x] Update all callers that previously called `BookRepo().load_daily_snapshots()` to call `SnapshotRepo().load_daily_snapshots()`

---

## `reports/Helper_Pdf_Loader.py` — `BookRawData`

Owned here because `Helper_Pdf_Loader.load()` is the producer.

- [x] Add near top of file:
  ```python
  from __future__ import annotations
  from typing import TypedDict
  from utils.Repo_Snapshot import DailySnapshotRow

  class BookRawData(TypedDict):
      asin: str
      title: str
      profit_pct: float             # e.g. 0.70
      snapshot_rows: list[DailySnapshotRow]  # oldest-first; at least 2 entries guaranteed
  ```
- [x] Update `load()` return annotation to `BookRawData | None`

---

## `reports/Helper_Pdf_Metrics.py` — `MonthlyRow`, `BookMetricsData`

Owned here because `Helper_Pdf_Metrics.compute()` is the producer of both.

- [x] Add near top of file:
  ```python
  from __future__ import annotations
  from datetime import date
  from typing import NamedTuple, TypedDict
  from utils.Repo_Snapshot import DailySnapshotRow
  from reports.Helper_Pdf_Loader import BookRawData

  class MonthlyRow(NamedTuple):
      label: str          # "Aug 2026"
      units_str: str      # "1,234"
      profit_str: str     # "$4,567.89"
      avg_str: str        # "$152.26" (avg daily profit for that month)
      days_with_data: int # number of days with at least one snapshot row

  class BookMetricsData(TypedDict):
      # carried through from BookRawData
      asin: str
      title: str
      profit_pct: float
      snapshot_rows: list[DailySnapshotRow]
      # derived series (same length as snapshot_rows, sliced to last DAYS entries for charts)
      dates: list[date]
      date_labels: list[str]        # "Aug 01" formatted
      units_per_day: list[int]
      profit_per_day: list[float]
      cumulative_units: list[int]
      cumulative_profit: list[float]
      # monthly summary (full history, complete months only)
      monthly_rows: list[MonthlyRow]
  ```
- [x] Update `compute()` signature: `def compute(self, data: BookRawData) -> BookMetricsData`

---

## Update remaining call sites

- [x] `reports/Helper_Pdf_Renderer.py` — import `BookMetricsData`, `MonthlyRow` from `reports.Helper_Pdf_Metrics`; replace `dict` annotation with `BookMetricsData`; replace bare `tuple` with `MonthlyRow`
- [x] `reports/Service_pdf_genFromAsin.py` — no annotation changes needed (types flow through helpers)

---

## Verification

- [x] `python -c "from utils.Repo_Snapshot import DailySnapshotRow, SnapshotRepo; from reports.Helper_Pdf_Loader import BookRawData; from reports.Helper_Pdf_Metrics import MonthlyRow, BookMetricsData"` — no import error
- [x] No bare `dict` return type annotations remain in any `reports/` file or in `load_daily_snapshots`
- [x] `mypy reports/ utils/Repo_Snapshot.py` (or `pyright`) — no type errors introduced by the new annotations
