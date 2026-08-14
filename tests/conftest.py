"""Shared pytest fixtures for the Author BSR Tracker test suite."""

from __future__ import annotations

import sys
from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Ensure the repo root is on sys.path so imports like `from utils.registry import BookRepo` work.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.scrape_bsr import BestSellerRank
from utils.registry import BookRepo


@pytest.fixture()
def tmp_db(tmp_path: Path) -> Generator[BookRepo, None, None]:
    """Fresh SQLite DB in a temp directory, fully initialised."""
    db_path = tmp_path / "test_tracker.db"
    repo = BookRepo(db_path=db_path)
    repo.init_db()
    yield repo


@pytest.fixture()
def sample_book() -> dict:
    """Canonical book dict with all required registration fields."""
    return {
        "email": "author@example.com",
        "title": "Atomic Habits",
        "asin": "0735211299",
        "profit_pct": 0.70,
        "current_price": 14.99,
    }


@pytest.fixture()
def sample_snapshots():
    """Factory that returns n BestSellerRank instances with staggered scraped_at."""

    def _factory(asin: str, n: int = 5) -> list[BestSellerRank]:
        base = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)
        return [
            BestSellerRank(
                asin=asin,
                rank=1000 + i * 100,
                category="Books > Business",
                price=14.99,
                scraped_at=(base + timedelta(days=i)).isoformat(),
            )
            for i in range(n)
        ]

    return _factory
