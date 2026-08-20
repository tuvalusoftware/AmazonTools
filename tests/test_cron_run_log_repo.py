"""Unit tests for utils/Repo_CronRunLog.py — CronRunLogRepo."""

from __future__ import annotations

from utils.registry import BookRepo
from utils.Repo_CronRunLog import CronRunLogRepo


def _make_repo(tmp_db: BookRepo) -> CronRunLogRepo:
    """Return a CronRunLogRepo pointed at the same DB as *tmp_db*."""
    return CronRunLogRepo(db_path=tmp_db._db_path)


def _save(
    repo: CronRunLogRepo,
    *,
    cron_type: str = "scrape_bsr",
    asin: str | None = "B000000001",
    trigger: str = "cron",
    started_at: str = "2026-08-01T00:00:00+00:00",
    finished_at: str = "2026-08-01T00:00:05+00:00",
    status: str = "success",
    detail: str | None = "1 rank(s) saved",
) -> None:
    repo.save(
        cron_type,
        asin=asin,
        trigger=trigger,
        started_at=started_at,
        finished_at=finished_at,
        status=status,
        detail=detail,
    )


def test_save_then_query_round_trips_all_fields(tmp_db: BookRepo) -> None:
    repo = _make_repo(tmp_db)
    _save(repo)

    results = repo.query()

    assert len(results) == 1
    row = results[0]
    assert row["cron_type"] == "scrape_bsr"
    assert row["asin"] == "B000000001"
    assert row["trigger"] == "cron"
    assert row["started_at"] == "2026-08-01T00:00:00+00:00"
    assert row["finished_at"] == "2026-08-01T00:00:05+00:00"
    assert row["status"] == "success"
    assert row["detail"] == "1 rank(s) saved"


def test_query_filters_by_cron_type(tmp_db: BookRepo) -> None:
    repo = _make_repo(tmp_db)
    _save(repo, cron_type="scrape_bsr", started_at="2026-08-01T00:00:00+00:00")
    _save(repo, cron_type="monthly_summary", started_at="2026-08-01T00:00:01+00:00")

    results = repo.query(cron_type="scrape_bsr")

    assert len(results) == 1
    assert results[0]["cron_type"] == "scrape_bsr"


def test_query_filters_by_asin_excludes_null_asin_rows(tmp_db: BookRepo) -> None:
    repo = _make_repo(tmp_db)
    _save(repo, asin="B0001", started_at="2026-08-01T00:00:00+00:00")
    _save(repo, cron_type="email_digest", asin=None, started_at="2026-08-01T00:00:01+00:00")

    results = repo.query(asin="B0001")

    assert len(results) == 1
    assert results[0]["asin"] == "B0001"


def test_query_filters_by_status(tmp_db: BookRepo) -> None:
    repo = _make_repo(tmp_db)
    _save(repo, status="success", started_at="2026-08-01T00:00:00+00:00")
    _save(repo, status="failure", started_at="2026-08-01T00:00:01+00:00")

    results = repo.query(status="failure")

    assert len(results) == 1
    assert results[0]["status"] == "failure"


def test_query_filters_by_time_range_inclusive(tmp_db: BookRepo) -> None:
    repo = _make_repo(tmp_db)
    _save(repo, started_at="2026-08-01T00:00:00+00:00")
    _save(repo, started_at="2026-08-02T00:00:00+00:00")
    _save(repo, started_at="2026-08-03T00:00:00+00:00")

    results = repo.query(
        start_time="2026-08-01T00:00:00+00:00",
        end_time="2026-08-02T00:00:00+00:00",
    )

    started_ats = {row["started_at"] for row in results}
    assert started_ats == {"2026-08-01T00:00:00+00:00", "2026-08-02T00:00:00+00:00"}


def test_query_combines_multiple_filters_with_and(tmp_db: BookRepo) -> None:
    repo = _make_repo(tmp_db)
    _save(repo, cron_type="scrape_bsr", asin="B0001", started_at="2026-08-01T00:00:00+00:00")
    _save(repo, cron_type="scrape_bsr", asin="B0002", started_at="2026-08-01T00:00:01+00:00")
    _save(repo, cron_type="monthly_summary", asin="B0001", started_at="2026-08-01T00:00:02+00:00")

    results = repo.query(cron_type="scrape_bsr", asin="B0001")

    assert len(results) == 1
    assert results[0]["cron_type"] == "scrape_bsr"
    assert results[0]["asin"] == "B0001"


def test_query_limit_caps_results_and_orders_newest_first(tmp_db: BookRepo) -> None:
    repo = _make_repo(tmp_db)
    for i in range(5):
        _save(repo, started_at=f"2026-08-0{i+1}T00:00:00+00:00")

    results = repo.query(limit=2)

    assert len(results) == 2
    assert results[0]["started_at"] == "2026-08-05T00:00:00+00:00"
    assert results[1]["started_at"] == "2026-08-04T00:00:00+00:00"


def test_save_twice_produces_two_distinct_rows_not_upsert(tmp_db: BookRepo) -> None:
    repo = _make_repo(tmp_db)
    _save(repo, cron_type="scrape_bsr", asin="B0001", started_at="2026-08-01T00:00:00+00:00")
    _save(repo, cron_type="scrape_bsr", asin="B0001", started_at="2026-08-01T00:00:01+00:00")

    results = repo.query(cron_type="scrape_bsr", asin="B0001")

    assert len(results) == 2
