"""
Persist scraped data to disk in JSON or CSV format.
"""

from __future__ import annotations

import csv
import dataclasses
import json
from datetime import datetime, timezone
from pathlib import Path

from config import settings
from utils.logger import get_logger

log = get_logger(__name__)


def save_results(asin: str, records: list) -> int:
    """Write *records* to OUTPUT_DIR/<asin>/<timestamp>.<format> and return count saved."""
    out_dir = Path(settings.OUTPUT_DIR) / asin
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    fmt = settings.OUTPUT_FORMAT.lower()

    if fmt == "csv":
        path = out_dir / f"{ts}.csv"
        _write_csv(path, records)
    else:
        path = out_dir / f"{ts}.json"
        _write_json(path, records)

    log.debug("Saved %d records → %s", len(records), path)
    return len(records)


def _write_json(path: Path, records: list) -> None:
    data = [dataclasses.asdict(r) for r in records]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_csv(path: Path, records: list) -> None:
    if not records:
        return
    rows = [dataclasses.asdict(r) for r in records]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
