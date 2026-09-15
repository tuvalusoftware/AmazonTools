"""Unit tests for utils/browser.py — _notify_session_expired."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from utils.browser import _notify_session_expired


def _settings_mock(*, amazon_email: str = "owner@example.com") -> MagicMock:
    settings_mock = MagicMock()
    settings_mock.AMAZON_EMAIL = amazon_email
    return settings_mock


class TestNotifySessionExpired:
    def test_sends_to_amazon_email(self, tmp_path: Path) -> None:
        marker = tmp_path / ".session_alert_last_sent"
        settings_mock = _settings_mock(amazon_email="owner@example.com")

        with (
            patch("utils.browser.settings", settings_mock),
            patch("utils.browser._ALERT_MARKER_PATH", str(marker)),
            patch("utils.browser.send_email") as mock_send,
        ):
            _notify_session_expired()

        mock_send.assert_called_once()
        kwargs = mock_send.call_args.kwargs
        assert kwargs["to"] == "owner@example.com"
        assert marker.exists()

    def test_skips_when_amazon_email_not_set(self, tmp_path: Path) -> None:
        marker = tmp_path / ".session_alert_last_sent"
        settings_mock = _settings_mock(amazon_email="")

        with (
            patch("utils.browser.settings", settings_mock),
            patch("utils.browser._ALERT_MARKER_PATH", str(marker)),
            patch("utils.browser.send_email") as mock_send,
        ):
            _notify_session_expired()

        mock_send.assert_not_called()
        assert not marker.exists()

    def test_throttles_within_window(self, tmp_path: Path) -> None:
        marker = tmp_path / ".session_alert_last_sent"
        marker.write_text(datetime.now(timezone.utc).isoformat())
        settings_mock = _settings_mock()

        with (
            patch("utils.browser.settings", settings_mock),
            patch("utils.browser._ALERT_MARKER_PATH", str(marker)),
            patch("utils.browser.send_email") as mock_send,
        ):
            _notify_session_expired()

        mock_send.assert_not_called()

    def test_resends_after_window_elapses(self, tmp_path: Path) -> None:
        marker = tmp_path / ".session_alert_last_sent"
        stale = datetime.now(timezone.utc) - timedelta(hours=13)
        marker.write_text(stale.isoformat())
        settings_mock = _settings_mock()

        with (
            patch("utils.browser.settings", settings_mock),
            patch("utils.browser._ALERT_MARKER_PATH", str(marker)),
            patch("utils.browser.send_email") as mock_send,
        ):
            _notify_session_expired()

        mock_send.assert_called_once()
