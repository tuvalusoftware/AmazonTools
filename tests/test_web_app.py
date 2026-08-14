"""Unit tests for web/app.py — FastAPI routes."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from web.app import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, follow_redirects=False)


# ---------------------------------------------------------------------------
# POST /register
# ---------------------------------------------------------------------------


def test_post_register_redirects_on_success(client: TestClient) -> None:
    """Valid form + successful ASIN lookup + successful insert → 303 redirect."""
    with (
        patch("web.app.search_asin", return_value=("Atomic Habits", "0735211299")),
        patch("web.app.repo") as mock_repo,
    ):
        mock_repo.register_book.return_value = True

        response = client.post(
            "/register",
            data={"email": "author@example.com", "title": "Atomic Habits", "profit_pct": "70"},
        )

    assert response.status_code == 303
    assert "/registered" in response.headers["location"]


def test_post_register_rerenders_on_asin_not_found(client: TestClient) -> None:
    """search_asin raising ValueError → 200 with 'Could not resolve ASIN' message."""
    with patch("web.app.search_asin", side_effect=ValueError("not found")):
        response = client.post(
            "/register",
            data={"email": "author@example.com", "title": "Unknown Book", "profit_pct": "70"},
        )

    assert response.status_code == 200
    assert "Could not resolve ASIN" in response.text


def test_post_register_rerenders_on_validation_error(client: TestClient) -> None:
    """profit_pct=-1 fails validation → 200 with an error message."""
    response = client.post(
        "/register",
        data={"email": "author@example.com", "title": "Atomic Habits", "profit_pct": "-1"},
    )

    assert response.status_code == 200
    assert "Error" in response.text or "error" in response.text.lower()


def test_post_register_passes_price_zero_to_repo(client: TestClient) -> None:
    """register_book is called with current_price=0.0 (C004A — no user price field)."""
    with (
        patch("web.app.search_asin", return_value=("Atomic Habits", "0735211299")),
        patch("web.app.repo") as mock_repo,
    ):
        mock_repo.register_book.return_value = True

        client.post(
            "/register",
            data={"email": "author@example.com", "title": "Atomic Habits", "profit_pct": "70"},
        )

    mock_repo.register_book.assert_called_once()
    call_kwargs = mock_repo.register_book.call_args[0][0]
    assert call_kwargs["current_price"] == 0.0


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
    with patch("web.app.repo") as mock_repo:
        mock_repo.unsubscribe_book.return_value = True
        mock_repo.load_active_books.return_value = []

        response = client.get(
            "/unsubscribe",
            params={"email": "author@example.com", "asin": "0735211299"},
        )

    assert response.status_code == 200
    assert "Unsubscribed" in response.text


def test_unsubscribe_all_mode(client: TestClient) -> None:
    """?email=… (no asin) with unsubscribe_email returning 2 → all-mode content."""
    with patch("web.app.repo") as mock_repo:
        mock_repo.unsubscribe_email.return_value = 2

        response = client.get(
            "/unsubscribe",
            params={"email": "author@example.com"},
        )

    assert response.status_code == 200
    assert "All emails unsubscribed" in response.text


def test_unsubscribe_not_found_mode(client: TestClient) -> None:
    """unsubscribe_book returning False and unsubscribe_email returning 0 → not-found content."""
    with patch("web.app.repo") as mock_repo:
        mock_repo.unsubscribe_book.return_value = False
        mock_repo.unsubscribe_email.return_value = 0

        response = client.get(
            "/unsubscribe",
            params={"email": "author@example.com", "asin": "0735211299"},
        )

    assert response.status_code == 200
    assert "Nothing to unsubscribe" in response.text
