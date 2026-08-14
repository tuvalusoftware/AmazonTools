"""Unit tests for jobs/email_digest.py — _build_digest_html and send_email."""

from __future__ import annotations

import smtplib
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from jobs.email_digest import _build_digest_html, send_email


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_book(
    *,
    email: str = "author@example.com",
    title: str = "Atomic Habits",
    asin: str = "0735211299",
    profit_pct: float = 70.0,
    current_price: float = 14.99,
) -> dict:
    return {
        "email": email,
        "title": title,
        "asin": asin,
        "profit_pct": profit_pct,
        "current_price": current_price,
    }


def _make_snapshot(
    *,
    asin: str = "0735211299",
    rank: int = 1000,
    category: str = "Books > Business",
    price: float = 14.99,
    scraped_at: str = "2026-08-14T00:00:00+00:00",
) -> dict:
    return {
        "asin": asin,
        "rank": rank,
        "category": category,
        "price": price,
        "scraped_at": scraped_at,
    }


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

class TestBuildDigestHtml:
    """Tests for _build_digest_html."""

    def _call(self, email: str, books: list[dict], snapshot: dict | None) -> str:
        mock_repo = MagicMock()
        mock_repo.load_latest_snapshot.return_value = snapshot
        with patch("jobs.email_digest.BookRepo", return_value=mock_repo):
            return _build_digest_html(email, books)

    # --- test_build_digest_html_renders_book_title ---

    def test_build_digest_html_renders_book_title(self) -> None:
        book = _make_book(title="Atomic Habits")
        html = self._call("author@example.com", [book], _make_snapshot())
        assert "Atomic Habits" in html

    # --- test_build_digest_html_includes_rank_formatted ---

    def test_build_digest_html_includes_rank_formatted(self) -> None:
        book = _make_book()
        html = self._call("author@example.com", [book], _make_snapshot(rank=1523))
        assert "#1,523" in html

    # --- test_build_digest_html_includes_unsubscribe_book_url ---

    def test_build_digest_html_includes_unsubscribe_book_url(self) -> None:
        email = "author@example.com"
        asin = "0735211299"
        book = _make_book(email=email, asin=asin)
        html = self._call(email, [book], _make_snapshot(asin=asin))
        assert "email=" in html
        assert "asin=" in html

    # --- test_build_digest_html_includes_unsubscribe_all_url ---

    def test_build_digest_html_includes_unsubscribe_all_url(self) -> None:
        email = "author@example.com"
        book = _make_book(email=email)
        html = self._call(email, [book], _make_snapshot())
        # The unsubscribe-all URL ends at email= with no asin param.
        # Simplest assertion: a URL with email= but no &asin= exists somewhere.
        import re
        unsubscribe_all_pattern = re.compile(r"unsubscribe\?email=[^&\"]+\"")
        assert unsubscribe_all_pattern.search(html), (
            "Expected an unsubscribe-all URL with only email= query param"
        )

    # --- test_build_digest_html_shows_no_rank_when_none ---

    def test_build_digest_html_shows_no_rank_when_none(self) -> None:
        book = _make_book()
        html = self._call("author@example.com", [book], None)
        assert "No rank data yet" in html

    # --- test_build_digest_html_computes_estimated_daily_profit ---

    def test_build_digest_html_computes_estimated_daily_profit(self) -> None:
        """A book at rank=1000, price=20.0, profit_pct=70.0 should produce a
        positive estimated daily profit rendered in the HTML."""
        book = _make_book(current_price=20.0, profit_pct=70.0)
        snapshot = _make_snapshot(rank=1000, price=20.0)
        html = self._call("author@example.com", [book], snapshot)
        # The template renders the Est. Daily Profit section only when > 0.
        assert "Est. Daily Profit" in html

    # --- test_build_digest_html_reads_price_from_snapshot ---

    def test_build_digest_html_reads_price_from_snapshot(self) -> None:
        """When snapshot carries price=14.99 the rendered email must show $14.99,
        even when tracked_books.current_price is 0.0."""
        book = _make_book(current_price=0.0)
        snapshot = _make_snapshot(price=14.99, rank=500)
        html = self._call("author@example.com", [book], snapshot)
        assert "$14.99" in html


# ---------------------------------------------------------------------------
# TestSendEmail
# ---------------------------------------------------------------------------

def _smtp_settings(*, port: int = 587) -> MagicMock:
    cfg = MagicMock()
    cfg.host = "smtp.example.com"
    cfg.port = port
    cfg.user = "user@example.com"
    cfg.password = "secret"
    cfg.from_addr = ""
    return cfg


class TestSendEmail:
    """Tests for send_email."""

    def _patch_smtp(self, port: int = 587):
        """Return a context-manager stack that patches settings and smtplib.SMTP."""
        settings_mock = MagicMock()
        settings_mock.smtp = _smtp_settings(port=port)
        smtp_instance = MagicMock()
        smtp_cm = MagicMock()
        smtp_cm.__enter__ = MagicMock(return_value=smtp_instance)
        smtp_cm.__exit__ = MagicMock(return_value=False)
        smtp_constructor = MagicMock(return_value=smtp_cm)
        return settings_mock, smtp_constructor, smtp_instance

    # --- test_send_email_html_only_uses_alternative_mime ---

    def test_send_email_html_only_uses_alternative_mime(self) -> None:
        settings_mock, smtp_constructor, smtp_instance = self._patch_smtp()
        captured: list = []

        def fake_sendmail(from_addr, to_list, msg_string):
            captured.append(msg_string)

        smtp_instance.sendmail.side_effect = fake_sendmail

        with (
            patch("jobs.email_digest.settings", settings_mock),
            patch("jobs.email_digest.smtplib.SMTP", smtp_constructor),
        ):
            send_email("to@example.com", "Subject", "<p>Hello</p>")

        assert captured, "sendmail was not called"
        assert "multipart/alternative" in captured[0]
        assert "multipart/mixed" not in captured[0]

    # --- test_send_email_with_attachment_uses_mixed_mime ---

    def test_send_email_with_attachment_uses_mixed_mime(self) -> None:
        settings_mock, smtp_constructor, smtp_instance = self._patch_smtp()
        captured: list = []

        def fake_sendmail(from_addr, to_list, msg_string):
            captured.append(msg_string)

        smtp_instance.sendmail.side_effect = fake_sendmail

        with (
            patch("jobs.email_digest.settings", settings_mock),
            patch("jobs.email_digest.smtplib.SMTP", smtp_constructor),
            patch.object(Path, "read_bytes", return_value=b"%PDF-fake"),
        ):
            send_email(
                "to@example.com",
                "Subject",
                "<p>Hello</p>",
                attachment=Path("report.pdf"),
            )

        assert captured, "sendmail was not called"
        assert "multipart/mixed" in captured[0]

    # --- test_send_email_with_attachment_includes_pdf_part ---

    def test_send_email_with_attachment_includes_pdf_part(self) -> None:
        settings_mock, smtp_constructor, smtp_instance = self._patch_smtp()
        captured: list = []

        def fake_sendmail(from_addr, to_list, msg_string):
            captured.append(msg_string)

        smtp_instance.sendmail.side_effect = fake_sendmail

        with (
            patch("jobs.email_digest.settings", settings_mock),
            patch("jobs.email_digest.smtplib.SMTP", smtp_constructor),
            patch.object(Path, "read_bytes", return_value=b"%PDF-fake"),
        ):
            send_email(
                "to@example.com",
                "Subject",
                "<p>Hello</p>",
                attachment=Path("report.pdf"),
            )

        assert captured, "sendmail was not called"
        msg_str = captured[0]
        assert 'filename="report.pdf"' in msg_str

    # --- test_send_email_logs_smtp_error_without_raising ---

    def test_send_email_logs_smtp_error_without_raising(self, caplog: pytest.LogCaptureFixture) -> None:
        settings_mock, smtp_constructor, smtp_instance = self._patch_smtp()
        smtp_instance.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Bad credentials")

        with (
            patch("jobs.email_digest.settings", settings_mock),
            patch("jobs.email_digest.smtplib.SMTP", smtp_constructor),
            caplog.at_level("ERROR", logger="jobs.email_digest"),
        ):
            send_email("to@example.com", "Subject", "<p>Hello</p>")

        assert any("SMTP error" in r.message or "error" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# TestRun
# ---------------------------------------------------------------------------

def _make_book_row(
    *,
    email: str = "author@example.com",
    title: str = "Atomic Habits",
    asin: str = "0735211299",
    profit_pct: float = 70.0,
    current_price: float = 14.99,
) -> dict:
    return {
        "email": email,
        "title": title,
        "asin": asin,
        "profit_pct": profit_pct,
        "current_price": current_price,
    }


class TestRun:
    """Tests for the run() job entry point in jobs/email_digest.py."""

    def _base_patches(self) -> dict:
        """Return a dict of patch targets that every test needs to silence I/O."""
        return {
            "jobs.email_digest.BookRepo": MagicMock(),
            "jobs.email_digest._build_digest_html": MagicMock(return_value="<html/>"),
            "jobs.email_digest.send_email": MagicMock(),
            "jobs.email_digest.Service_Pdf_GenFromAsin": MagicMock(),
        }

    # --- test_run_skips_when_no_active_books ---

    def test_run_skips_when_no_active_books(self, caplog: pytest.LogCaptureFixture) -> None:
        from jobs.email_digest import run

        mock_repo = MagicMock()
        mock_repo.load_active_books.return_value = []

        with (
            patch("jobs.email_digest.BookRepo", return_value=mock_repo),
            patch("jobs.email_digest.send_email") as mock_send,
            patch("jobs.email_digest.Service_Pdf_GenFromAsin"),
            caplog.at_level("WARNING", logger="jobs.email_digest"),
        ):
            run()

        mock_send.assert_not_called()
        assert any("No active books" in r.message for r in caplog.records)

    # --- test_run_groups_books_by_email ---

    def test_run_groups_books_by_email(self) -> None:
        from jobs.email_digest import run

        books = [
            _make_book_row(email="alice@example.com", asin="ASIN001"),
            _make_book_row(email="alice@example.com", asin="ASIN002"),
            _make_book_row(email="bob@example.com",   asin="ASIN003"),
        ]

        mock_repo = MagicMock()
        mock_repo.load_active_books.return_value = books

        with (
            patch("jobs.email_digest.BookRepo", return_value=mock_repo),
            patch("jobs.email_digest._build_digest_html", return_value="<html/>"),
            patch("jobs.email_digest.send_email") as mock_send,
            patch("jobs.email_digest.Service_Pdf_GenFromAsin"),
        ):
            run()

        assert mock_send.call_count == 2
        called_addrs = {c.args[0] for c in mock_send.call_args_list}
        assert called_addrs == {"alice@example.com", "bob@example.com"}

    # --- test_run_deletes_temp_pdf_after_send ---

    def test_run_deletes_temp_pdf_after_send(self) -> None:
        import tempfile as _tempfile

        from jobs.email_digest import run

        books = [_make_book_row()]

        mock_repo = MagicMock()
        mock_repo.load_active_books.return_value = books

        # Create a real temp file that Service_Pdf_GenFromAsin would "produce".
        real_tmp = _tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        real_tmp_path = Path(real_tmp.name)
        real_tmp.close()

        # Intercept NamedTemporaryFile so we can steer the rename destination.
        original_ntf = _tempfile.NamedTemporaryFile

        def fake_ntf(**kwargs):
            return original_ntf(**kwargs)

        # The rename in run() moves tmp_pdf → bsr_report_<date>.pdf in the same dir.
        # We just need the final path to still exist before run() deletes it.
        renamed: list[Path] = []

        original_rename = Path.rename

        def capturing_rename(self, target):
            result = original_rename(self, target)
            renamed.append(result)
            return result

        with (
            patch("jobs.email_digest.BookRepo", return_value=mock_repo),
            patch("jobs.email_digest._build_digest_html", return_value="<html/>"),
            patch("jobs.email_digest.send_email"),
            patch("jobs.email_digest.Service_Pdf_GenFromAsin") as MockPdf,
            patch.object(Path, "rename", capturing_rename),
        ):
            # Service_Pdf_GenFromAsin().run() is a no-op; the real temp file is
            # already on disk from NamedTemporaryFile above, so we patch the
            # constructor to also steer which path gets used.
            mock_pdf_instance = MagicMock()
            MockPdf.return_value = mock_pdf_instance

            # Override NamedTemporaryFile to return our pre-created file handle.
            import io

            class _FakeTmp:
                name = str(real_tmp_path)

                def __enter__(self):
                    return self

                def __exit__(self, *_):
                    pass

            with patch("jobs.email_digest.tempfile.NamedTemporaryFile", return_value=_FakeTmp()):
                run()

        # After run() the final (renamed) pdf must be gone.
        if renamed:
            assert not renamed[0].exists(), "Expected temp PDF to be deleted after run()"
        else:
            assert not real_tmp_path.exists(), "Expected temp PDF to be deleted after run()"

    # --- test_run_subject_contains_today_date ---

    def test_run_subject_contains_today_date(self) -> None:
        from datetime import date

        from jobs.email_digest import run

        today_iso = date.today().strftime("%Y-%m-%d")
        books = [_make_book_row()]

        mock_repo = MagicMock()
        mock_repo.load_active_books.return_value = books

        with (
            patch("jobs.email_digest.BookRepo", return_value=mock_repo),
            patch("jobs.email_digest._build_digest_html", return_value="<html/>"),
            patch("jobs.email_digest.send_email") as mock_send,
            patch("jobs.email_digest.Service_Pdf_GenFromAsin"),
        ):
            run()

        assert mock_send.call_count >= 1
        subject = mock_send.call_args_list[0].args[1]
        assert today_iso in subject
