"""Unit tests for reports/Service_pdf_genFromAsin.py — Service_Pdf_GenFromAsin."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from reports.Service_pdf_genFromAsin import Service_Pdf_GenFromAsin


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_book(asin: str) -> dict:
    return {"asin": asin, "title": f"Book {asin}", "profit_pct": 0.70}



_SENTINEL = object()


def _build_mocks(load_return: object = _SENTINEL) -> tuple[MagicMock, MagicMock, MagicMock, MagicMock]:
    """Return a tuple of mock classes wired for the happy path."""
    resolved_return = MagicMock() if load_return is _SENTINEL else load_return
    MockLoader = MagicMock()
    MockLoader.return_value.load.return_value = resolved_return

    MockMetrics = MagicMock()
    MockMetrics.return_value.compute.return_value = MagicMock()

    MockRenderer = MagicMock()

    MockPdfPages = MagicMock()
    MockPdfPages.return_value.__enter__ = lambda s: s
    MockPdfPages.return_value.__exit__ = MagicMock(return_value=False)

    return MockLoader, MockMetrics, MockRenderer, MockPdfPages


# ---------------------------------------------------------------------------
# test_run_returns_output_path
# ---------------------------------------------------------------------------


def test_run_returns_output_path(tmp_path: Path) -> None:
    """run() returns a Path object pointing to the written PDF."""
    output = tmp_path / "report.pdf"
    MockLoader, MockMetrics, MockRenderer, MockPdfPages = _build_mocks()

    with patch("reports.Service_pdf_genFromAsin.BookRepo") as MockBookRepo, \
         patch("reports.Service_pdf_genFromAsin.Helper_Pdf_Loader", MockLoader), \
         patch("reports.Service_pdf_genFromAsin.Helper_Pdf_Metrics", MockMetrics), \
         patch("reports.Service_pdf_genFromAsin.Helper_Pdf_Renderer", MockRenderer), \
         patch("reports.Service_pdf_genFromAsin.PdfPages", MockPdfPages):

        MockBookRepo.return_value.load_active_books.return_value = [_make_book("B0001")]

        result = Service_Pdf_GenFromAsin(output_path=output).run()

    assert isinstance(result, Path)
    assert result == output.resolve()


# ---------------------------------------------------------------------------
# test_run_skips_asin_with_no_data
# ---------------------------------------------------------------------------


def test_run_skips_asin_with_no_data(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """When loader.load() returns None, render_book is not called and WARNING is logged."""
    output = tmp_path / "report.pdf"
    MockLoader, MockMetrics, MockRenderer, MockPdfPages = _build_mocks(load_return=None)

    with caplog.at_level(logging.WARNING, logger="reports.Service_pdf_genFromAsin"), \
         patch("reports.Service_pdf_genFromAsin.BookRepo") as MockBookRepo, \
         patch("reports.Service_pdf_genFromAsin.Helper_Pdf_Loader", MockLoader), \
         patch("reports.Service_pdf_genFromAsin.Helper_Pdf_Metrics", MockMetrics), \
         patch("reports.Service_pdf_genFromAsin.Helper_Pdf_Renderer", MockRenderer), \
         patch("reports.Service_pdf_genFromAsin.PdfPages", MockPdfPages):

        MockBookRepo.return_value.load_active_books.return_value = [_make_book("B0002")]

        Service_Pdf_GenFromAsin(output_path=output).run()

    MockRenderer.return_value.render_book.assert_not_called()
    assert any("B0002" in record.message for record in caplog.records)
    assert any(record.levelno == logging.WARNING for record in caplog.records)


# ---------------------------------------------------------------------------
# test_run_filters_to_single_asin
# ---------------------------------------------------------------------------


def test_run_filters_to_single_asin(tmp_path: Path) -> None:
    """When asin_filter is set, loader.load is called exactly once with that ASIN."""
    output = tmp_path / "report.pdf"
    MockLoader, MockMetrics, MockRenderer, MockPdfPages = _build_mocks()

    with patch("reports.Service_pdf_genFromAsin.BookRepo") as MockBookRepo, \
         patch("reports.Service_pdf_genFromAsin.Helper_Pdf_Loader", MockLoader), \
         patch("reports.Service_pdf_genFromAsin.Helper_Pdf_Metrics", MockMetrics), \
         patch("reports.Service_pdf_genFromAsin.Helper_Pdf_Renderer", MockRenderer), \
         patch("reports.Service_pdf_genFromAsin.PdfPages", MockPdfPages):

        MockBookRepo.return_value.load_active_books.return_value = [
            _make_book("B0001"),
            _make_book("B0002"),
        ]

        Service_Pdf_GenFromAsin(asin_filter="B0001", output_path=output).run()

    MockLoader.return_value.load.assert_called_once()
    called_asin = MockLoader.return_value.load.call_args[0][0]
    assert called_asin == "B0001"


def test_run_filters_to_asin_list(tmp_path: Path) -> None:
    """When asin_filter is a list, loader.load is called once per listed ASIN."""
    output = tmp_path / "report.pdf"
    MockLoader, MockMetrics, MockRenderer, MockPdfPages = _build_mocks()

    with patch("reports.Service_pdf_genFromAsin.BookRepo") as MockBookRepo, \
         patch("reports.Service_pdf_genFromAsin.Helper_Pdf_Loader", MockLoader), \
         patch("reports.Service_pdf_genFromAsin.Helper_Pdf_Metrics", MockMetrics), \
         patch("reports.Service_pdf_genFromAsin.Helper_Pdf_Renderer", MockRenderer), \
         patch("reports.Service_pdf_genFromAsin.PdfPages", MockPdfPages):

        MockBookRepo.return_value.load_active_books.return_value = [
            _make_book("B0001"),
            _make_book("B0002"),
            _make_book("B0003"),
        ]

        Service_Pdf_GenFromAsin(
            asin_filter=["B0001", "B0003"], output_path=output
        ).run()

    MockBookRepo.return_value.load_active_books.assert_not_called()
    called_asins = [c.args[0] for c in MockLoader.return_value.load.call_args_list]
    assert called_asins == ["B0001", "B0003"]


# ---------------------------------------------------------------------------
# test_run_all_active_books_when_no_filter
# ---------------------------------------------------------------------------


def test_run_all_active_books_when_no_filter(tmp_path: Path) -> None:
    """When asin_filter is None, loader.load is called once per active book."""
    output = tmp_path / "report.pdf"
    MockLoader, MockMetrics, MockRenderer, MockPdfPages = _build_mocks()

    with patch("reports.Service_pdf_genFromAsin.BookRepo") as MockBookRepo, \
         patch("reports.Service_pdf_genFromAsin.Helper_Pdf_Loader", MockLoader), \
         patch("reports.Service_pdf_genFromAsin.Helper_Pdf_Metrics", MockMetrics), \
         patch("reports.Service_pdf_genFromAsin.Helper_Pdf_Renderer", MockRenderer), \
         patch("reports.Service_pdf_genFromAsin.PdfPages", MockPdfPages):

        MockBookRepo.return_value.load_active_books.return_value = [
            _make_book("B0001"),
            _make_book("B0002"),
        ]

        Service_Pdf_GenFromAsin(asin_filter=None, output_path=output).run()

    assert MockLoader.return_value.load.call_count == 2


# ---------------------------------------------------------------------------
# test_run_uses_custom_output_path
# ---------------------------------------------------------------------------


def test_run_uses_custom_output_path(tmp_path: Path) -> None:
    """run() returns the resolved custom output path that was passed in."""
    custom_output = tmp_path / "custom.pdf"
    MockLoader, MockMetrics, MockRenderer, MockPdfPages = _build_mocks()

    with patch("reports.Service_pdf_genFromAsin.BookRepo") as MockBookRepo, \
         patch("reports.Service_pdf_genFromAsin.Helper_Pdf_Loader", MockLoader), \
         patch("reports.Service_pdf_genFromAsin.Helper_Pdf_Metrics", MockMetrics), \
         patch("reports.Service_pdf_genFromAsin.Helper_Pdf_Renderer", MockRenderer), \
         patch("reports.Service_pdf_genFromAsin.PdfPages", MockPdfPages):

        MockBookRepo.return_value.load_active_books.return_value = [_make_book("B0001")]

        result = Service_Pdf_GenFromAsin(output_path=custom_output).run()

    assert result == custom_output.resolve()
