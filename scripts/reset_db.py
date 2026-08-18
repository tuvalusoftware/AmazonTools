"""
Reset the SQLite database.

Drops all tables (tracked_books, bsr_snapshots) then re-creates the schema
via BookRepo.init_db().  Requires explicit --yes flag to prevent accidents.

Usage:
    python -m scripts.reset_db --yes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from config import settings
from utils.registry import BookRepo


def reset(db_path: Path) -> None:
    print(f"Resetting database at {db_path} …")
    if db_path.exists():
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute("DROP TABLE IF EXISTS bsr_snapshots")
            conn.execute("DROP TABLE IF EXISTS tracked_books")
            conn.commit()
        finally:
            conn.close()
        print("  dropped: tracked_books, bsr_snapshots")
    else:
        print("  database file does not exist yet — will create fresh")

    BookRepo(db_path).init_db()
    print("  re-created schema via BookRepo.init_db()")
    print("Done.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset the tracker database.")
    parser.add_argument(
        "--yes", action="store_true",
        help="Confirm destructive reset (required)",
    )
    args = parser.parse_args()

    if not args.yes:
        print("ERROR: pass --yes to confirm the destructive reset.", file=sys.stderr)
        sys.exit(1)

    reset(Path(settings.DB_PATH))


if __name__ == "__main__":
    main()
