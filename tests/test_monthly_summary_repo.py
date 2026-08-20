"""Unit tests for utils/Repo_MonthlySummary.py — MonthlySummaryRepo."""

from __future__ import annotations

from utils.registry import BookRepo
from utils.Repo_MonthlySummary import MonthlySummaryRepo


def _make_repo(tmp_db: BookRepo) -> MonthlySummaryRepo:
    """Return a MonthlySummaryRepo pointed at the same DB as *tmp_db*."""
    return MonthlySummaryRepo(db_path=tmp_db._db_path)


# ---------------------------------------------------------------------------
# test_save_then_get_round_trips_values
# ---------------------------------------------------------------------------


def test_save_then_get_round_trips_values(tmp_db: BookRepo) -> None:
    repo = _make_repo(tmp_db)
    repo.save(
        asin="B000000001",
        year=2026,
        month=7,
        total_units=42,
        total_profit=123.45,
        days_with_data=31,
    )

    result = repo.get("B000000001", 2026, 7)

    assert result == {
        "asin": "B000000001",
        "year": 2026,
        "month": 7,
        "total_units": 42,
        "total_profit": 123.45,
        "days_with_data": 31,
    }


# ---------------------------------------------------------------------------
# test_save_is_upsert_not_insert_duplicate
# ---------------------------------------------------------------------------


def test_save_is_upsert_not_insert_duplicate(tmp_db: BookRepo) -> None:
    repo = _make_repo(tmp_db)
    asin = "B000000002"
    repo.save(asin=asin, year=2026, month=7, total_units=10, total_profit=50.0, days_with_data=10)
    repo.save(asin=asin, year=2026, month=7, total_units=99, total_profit=999.99, days_with_data=31)

    result = repo.get(asin, 2026, 7)
    assert result["total_units"] == 99
    assert result["total_profit"] == 999.99
    assert result["days_with_data"] == 31

    conn = repo._get_conn()
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM book_monthly_summary WHERE asin = ? AND year = ? AND month = ?",
            (asin, 2026, 7),
        ).fetchone()[0]
    finally:
        conn.close()
    assert count == 1


# ---------------------------------------------------------------------------
# test_get_returns_none_for_unsaved_month
# ---------------------------------------------------------------------------


def test_get_returns_none_for_unsaved_month(tmp_db: BookRepo) -> None:
    repo = _make_repo(tmp_db)
    assert repo.get("B000000003", 2026, 7) is None


# ---------------------------------------------------------------------------
# test_get_many_returns_all_months_keyed_by_year_month
# ---------------------------------------------------------------------------


def test_get_many_returns_all_months_keyed_by_year_month(tmp_db: BookRepo) -> None:
    repo = _make_repo(tmp_db)
    asin = "B000000004"
    other_asin = "B000000005"
    repo.save(asin=asin, year=2026, month=6, total_units=5, total_profit=10.0, days_with_data=30)
    repo.save(asin=asin, year=2026, month=7, total_units=6, total_profit=20.0, days_with_data=31)
    repo.save(asin=other_asin, year=2026, month=7, total_units=1, total_profit=1.0, days_with_data=1)

    result = repo.get_many(asin)

    assert set(result.keys()) == {(2026, 6), (2026, 7)}
    assert result[(2026, 6)]["total_units"] == 5
    assert result[(2026, 7)]["total_units"] == 6
