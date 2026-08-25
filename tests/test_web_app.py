"""Unit tests for web/app.py — FastAPI routes."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from web.app import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, follow_redirects=False)


# ---------------------------------------------------------------------------
# POST /register
# ---------------------------------------------------------------------------


def test_post_register_returns_pending_on_valid_form(client: TestClient) -> None:
    """Valid form data → 200 with pending page; RegisterService.run is called."""
    with patch("web.register_service.RegisterService.run") as mock_run:
        response = client.post(
            "/register",
            data={
                "email": "author@example.com",
                "title": "Atomic Habits",
                "profit_pct": "70",
            },
        )

    assert response.status_code == 200
    assert "received" in response.text.lower()
    mock_run.assert_called_once()


def test_post_register_rerenders_on_validation_error(client: TestClient) -> None:
    """profit_pct=-1 fails validation → 200 with an error message, no task enqueued."""
    response = client.post(
        "/register",
        data={
            "email": "author@example.com",
            "title": "Atomic Habits",
            "profit_pct": "-1",
        },
    )

    assert response.status_code == 200
    assert "error" in response.text.lower()


# ---------------------------------------------------------------------------
# GET /registered
# ---------------------------------------------------------------------------


def test_get_registered_shows_title(client: TestClient) -> None:
    """GET /registered?title=Atomic+Habits must include the title in the response body."""
    response = client.get("/registered?title=Atomic+Habits")

    assert response.status_code == 200
    assert "Atomic Habits" in response.text


# ---------------------------------------------------------------------------
# GET /unsubscribe
# ---------------------------------------------------------------------------


def test_unsubscribe_book_mode(client: TestClient) -> None:
    """?email=…&asin=… with unsubscribe_book returning True → book-mode content."""
    mock_repo = MagicMock()
    mock_repo.unsubscribe_book.return_value = True
    mock_repo.load_active_books.return_value = []

    with patch("web.app.BookRepo", return_value=mock_repo):
        response = client.get(
            "/unsubscribe",
            params={"email": "author@example.com", "asin": "0735211299"},
        )

    assert response.status_code == 200
    assert "Unsubscribed" in response.text


def test_unsubscribe_all_mode(client: TestClient) -> None:
    """?email=… (no asin) with unsubscribe_email returning 2 → all-mode content."""
    mock_repo = MagicMock()
    mock_repo.unsubscribe_email.return_value = 2

    with patch("web.app.BookRepo", return_value=mock_repo):
        response = client.get(
            "/unsubscribe",
            params={"email": "author@example.com"},
        )

    assert response.status_code == 200
    assert "All emails unsubscribed" in response.text


def test_unsubscribe_not_found_mode(client: TestClient) -> None:
    """unsubscribe_book returning False → not-found content."""
    mock_repo = MagicMock()
    mock_repo.unsubscribe_book.return_value = False

    with patch("web.app.BookRepo", return_value=mock_repo):
        response = client.get(
            "/unsubscribe",
            params={"email": "author@example.com", "asin": "0735211299"},
        )

    assert response.status_code == 200
    assert "Nothing to unsubscribe" in response.text


# ---------------------------------------------------------------------------
# RegisterService.run — pipeline unit tests
# ---------------------------------------------------------------------------


def _make_service() -> "RegisterService":  # noqa: F821
    from web.register_service import RegisterService

    return RegisterService(
        email="author@example.com",
        title="Atomic Habits",
        profit_val=70.0,
    )


def test_register_service_run_success() -> None:
    """T1 — ASIN found + new insert → confirmed email sent, no not-found/duplicate."""
    svc = _make_service()
    mock_repo = MagicMock()
    mock_repo.register_book.return_value = True

    with (
        patch("web.register_service.SearchAsinService.search", return_value=("Atomic Habits", "B0123456")),
        patch("web.register_service.BookRepo", return_value=mock_repo),
        patch("web.register_service.send_email") as mock_send,
    ):
        svc.run()

    mock_send.assert_called_once()
    subject, _ = mock_send.call_args.args[1], mock_send.call_args.args[2]
    assert "registered" in subject.lower()
    mock_repo.register_book.assert_called_once()


def test_register_service_run_not_found_value_error() -> None:
    """T2 — SearchAsinService raises ValueError → not-found email sent, no DB write."""
    svc = _make_service()
    mock_repo = MagicMock()

    with (
        patch("web.register_service.SearchAsinService.search", side_effect=ValueError("no results")),
        patch("web.register_service.BookRepo", return_value=mock_repo),
        patch("web.register_service.send_email") as mock_send,
    ):
        svc.run()

    mock_send.assert_called_once()
    subject, _ = mock_send.call_args.args[1], mock_send.call_args.args[2]
    assert "could not find" in subject.lower()
    mock_repo.register_book.assert_not_called()


def test_register_service_run_duplicate() -> None:
    """T3 — register_book returns False → duplicate email sent, single DB call."""
    svc = _make_service()
    mock_repo = MagicMock()
    mock_repo.register_book.return_value = False

    with (
        patch("web.register_service.SearchAsinService.search", return_value=("Atomic Habits", "B0123456")),
        patch("web.register_service.BookRepo", return_value=mock_repo),
        patch("web.register_service.send_email") as mock_send,
    ):
        svc.run()

    mock_send.assert_called_once()
    subject, _ = mock_send.call_args.args[1], mock_send.call_args.args[2]
    assert "already tracking" in subject.lower()
    mock_repo.register_book.assert_called_once()


def test_register_service_run_unexpected_error_no_crash() -> None:
    """T4 — SearchAsinService raises RuntimeError → not-found email sent, no crash."""
    svc = _make_service()
    mock_repo = MagicMock()

    with (
        patch("web.register_service.SearchAsinService.search", side_effect=RuntimeError("timeout")),
        patch("web.register_service.BookRepo", return_value=mock_repo),
        patch("web.register_service.send_email") as mock_send,
    ):
        svc.run()

    mock_send.assert_called_once()
    subject, _ = mock_send.call_args.args[1], mock_send.call_args.args[2]
    assert "could not find" in subject.lower()
    mock_repo.register_book.assert_not_called()
