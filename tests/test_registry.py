"""Unit tests for utils/registry.py — BookRepo."""

from __future__ import annotations

import sqlite3

from utils.registry import BookRepo


def test_init_db_creates_tables(tmp_db: BookRepo) -> None:
    """init_db() must create both tracked_books and bsr_snapshots tables."""
    conn = sqlite3.connect(str(tmp_db._db_path))
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        conn.close()

    assert "tracked_books" in tables
    assert "bsr_snapshots" in tables


def test_init_db_idempotent(tmp_db: BookRepo) -> None:
    """Calling init_db() a second time on the same DB path must not raise."""
    tmp_db.init_db()


# ---------------------------------------------------------------------------
# register_book
# ---------------------------------------------------------------------------


def test_register_book_returns_true_on_insert(
    tmp_db: BookRepo, sample_book: dict
) -> None:
    """Registering a new book returns True and persists an active=1 row."""
    result = tmp_db.register_book(sample_book)

    assert result is True

    rows = tmp_db.load_active_books()
    assert len(rows) == 1
    assert rows[0]["asin"] == sample_book["asin"]
    assert rows[0]["active"] == 1


def test_register_book_returns_false_on_active_duplicate(
    tmp_db: BookRepo, sample_book: dict
) -> None:
    """Registering the same active ASIN a second time returns False."""
    tmp_db.register_book(sample_book)
    result = tmp_db.register_book(sample_book)

    assert result is False
    assert len(tmp_db.load_active_books()) == 1


def test_register_book_reactivates_inactive(
    tmp_db: BookRepo, sample_book: dict
) -> None:
    """Re-registering an unsubscribed ASIN returns True and sets active=1."""
    tmp_db.register_book(sample_book)
    tmp_db.unsubscribe_book(sample_book["email"], sample_book["asin"])
    assert tmp_db.load_active_books() == []

    result = tmp_db.register_book(sample_book)

    assert result is True
    rows = tmp_db.load_active_books()
    assert len(rows) == 1
    assert rows[0]["asin"] == sample_book["asin"]
    assert rows[0]["active"] == 1


# ---------------------------------------------------------------------------
# unsubscribe_book
# ---------------------------------------------------------------------------


def test_unsubscribe_book_returns_true(tmp_db: BookRepo, sample_book: dict) -> None:
    """Unsubscribing an active book returns True and sets active=0."""
    tmp_db.register_book(sample_book)
    result = tmp_db.unsubscribe_book(sample_book["email"], sample_book["asin"])

    assert result is True
    assert tmp_db.load_active_books() == []


def test_unsubscribe_book_returns_false_when_not_found(tmp_db: BookRepo) -> None:
    """Unsubscribing an ASIN that was never registered returns False."""
    result = tmp_db.unsubscribe_book("nobody@example.com", "NOTEXIST")

    assert result is False


def test_unsubscribe_book_only_affects_matching_row(
    tmp_db: BookRepo, sample_book: dict
) -> None:
    """Unsubscribing one ASIN must not change the other book's active status."""
    book_b = {**sample_book, "asin": "B000000001", "title": "Second Book"}
    tmp_db.register_book(sample_book)
    tmp_db.register_book(book_b)

    tmp_db.unsubscribe_book(sample_book["email"], sample_book["asin"])

    active_asins = {row["asin"] for row in tmp_db.load_active_books()}
    assert sample_book["asin"] not in active_asins
    assert book_b["asin"] in active_asins


# ---------------------------------------------------------------------------
# unsubscribe_email
# ---------------------------------------------------------------------------


def test_unsubscribe_email_returns_count(
    tmp_db: BookRepo, sample_book: dict
) -> None:
    """unsubscribe_email deactivates all active books for an email and returns the count."""
    books = [
        {**sample_book, "asin": f"B00000000{i}", "title": f"Book {i}"}
        for i in range(3)
    ]
    for b in books:
        tmp_db.register_book(b)

    result = tmp_db.unsubscribe_email(sample_book["email"])

    assert result == 3
    assert tmp_db.load_active_books() == []


def test_unsubscribe_email_returns_zero_when_none_active(
    tmp_db: BookRepo, sample_book: dict
) -> None:
    """unsubscribe_email returns 0 when all books are already inactive."""
    tmp_db.register_book(sample_book)
    tmp_db.unsubscribe_email(sample_book["email"])

    result = tmp_db.unsubscribe_email(sample_book["email"])

    assert result == 0


# ---------------------------------------------------------------------------
# load_active_books
# ---------------------------------------------------------------------------


def test_load_active_books_excludes_inactive(
    tmp_db: BookRepo, sample_book: dict
) -> None:
    """load_active_books() must not return rows with active=0."""
    book_b = {**sample_book, "asin": "B000000001", "title": "Second Book"}
    tmp_db.register_book(sample_book)
    tmp_db.register_book(book_b)
    tmp_db.unsubscribe_book(sample_book["email"], sample_book["asin"])

    rows = tmp_db.load_active_books()

    assert len(rows) == 1
    assert rows[0]["asin"] == book_b["asin"]


def test_load_active_books_empty_db(tmp_db: BookRepo) -> None:
    """load_active_books() returns an empty list on a fresh DB."""
    assert tmp_db.load_active_books() == []


def test_load_active_books_returns_plain_dicts(
    tmp_db: BookRepo, sample_book: dict
) -> None:
    """Each element returned by load_active_books() must be a plain dict."""
    tmp_db.register_book(sample_book)

    rows = tmp_db.load_active_books()

    assert len(rows) == 1
    assert isinstance(rows[0], dict)


# ---------------------------------------------------------------------------
# save_bsr_snapshots
# ---------------------------------------------------------------------------


def test_save_bsr_snapshots_returns_count(
    tmp_db: BookRepo, sample_snapshots
) -> None:
    """save_bsr_snapshots() returns the number of rows inserted."""
    snaps = sample_snapshots("0735211299", n=3)
    result = tmp_db.save_bsr_snapshots(snaps)

    assert result == 3


def test_save_bsr_snapshots_inserts_all_rows(
    tmp_db: BookRepo, sample_snapshots
) -> None:
    """All passed snapshots must be persisted in bsr_snapshots."""
    import sqlite3

    snaps = sample_snapshots("0735211299", n=3)
    tmp_db.save_bsr_snapshots(snaps)

    conn = sqlite3.connect(str(tmp_db._db_path))
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM bsr_snapshots WHERE asin=?", ("0735211299",)
        ).fetchone()[0]
    finally:
        conn.close()

    assert count == 3


def test_save_bsr_snapshots_persists_price(
    tmp_db: BookRepo, sample_snapshots
) -> None:
    """The price field on each BestSellerRank must be stored correctly."""
    snaps = sample_snapshots("0735211299", n=1)
    assert snaps[0].price == 14.99

    tmp_db.save_bsr_snapshots(snaps)

    latest = tmp_db.load_latest_snapshot("0735211299")
    assert latest is not None
    assert latest["price"] == 14.99


# ---------------------------------------------------------------------------
# load_latest_snapshot
# ---------------------------------------------------------------------------


def test_load_latest_snapshot_returns_most_recent(
    tmp_db: BookRepo, sample_snapshots
) -> None:
    """load_latest_snapshot() returns the snapshot with the latest scraped_at."""
    snaps = sample_snapshots("0735211299", n=3)
    tmp_db.save_bsr_snapshots(snaps)

    latest = tmp_db.load_latest_snapshot("0735211299")

    assert latest is not None
    assert latest["scraped_at"] == snaps[-1].scraped_at


def test_load_latest_snapshot_returns_none_when_empty(tmp_db: BookRepo) -> None:
    """load_latest_snapshot() returns None when no rows exist for the ASIN."""
    result = tmp_db.load_latest_snapshot("NOTEXIST")

    assert result is None
