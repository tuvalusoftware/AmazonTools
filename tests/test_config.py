"""Unit tests for config.py — Settings and SmtpSettings."""

from __future__ import annotations

from config import Settings, SmtpSettings


# ---------------------------------------------------------------------------
# SmtpSettings defaults
# ---------------------------------------------------------------------------


def test_smtp_settings_defaults() -> None:
    smtp = SmtpSettings()
    assert smtp.host == "smtp.gmail.com"
    assert smtp.port == 587


# ---------------------------------------------------------------------------
# DB_PATH default
# ---------------------------------------------------------------------------


def test_db_path_default() -> None:
    s = Settings()
    assert "tracker.db" in s.DB_PATH
