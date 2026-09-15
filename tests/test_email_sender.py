"""Unit tests for utils/email_sender.py — send_email."""

from __future__ import annotations

import smtplib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from utils.email_sender import send_email


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
            patch("utils.email_sender.settings", settings_mock),
            patch("utils.email_sender.smtplib.SMTP", smtp_constructor),
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
            patch("utils.email_sender.settings", settings_mock),
            patch("utils.email_sender.smtplib.SMTP", smtp_constructor),
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
            patch("utils.email_sender.settings", settings_mock),
            patch("utils.email_sender.smtplib.SMTP", smtp_constructor),
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
            patch("utils.email_sender.settings", settings_mock),
            patch("utils.email_sender.smtplib.SMTP", smtp_constructor),
            caplog.at_level("ERROR", logger="utils.email_sender"),
        ):
            send_email("to@example.com", "Subject", "<p>Hello</p>")

        assert any("SMTP error" in r.message or "error" in r.message.lower() for r in caplog.records)
