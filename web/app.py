"""
FastAPI web application — Author BSR Tracker registration UI.

Routes
------
GET  /              — render registration form
POST /register      — validate form, resolve ASIN, save to registry
GET  /registered    — confirmation page (query param: title)
GET  /unsubscribe   — handle unsubscribe links from email digest
                      ?email=<email>               → unsubscribe all
                      ?email=<email>&asin=<asin>   → unsubscribe one book
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from scripts.lookup_asin import search_asin
from utils.logger import get_logger
from utils.registry import BookRepo

log = get_logger(__name__)

app = FastAPI(title="Author BSR Tracker")
templates = Jinja2Templates(directory="web/templates")
repo = BookRepo()


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #


def _render(request: Request, template: str, **ctx: Any) -> HTMLResponse:
    return templates.TemplateResponse(request, template, dict(ctx))


# ------------------------------------------------------------------ #
# Routes                                                               #
# ------------------------------------------------------------------ #


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return _render(request, "register.html")


@app.post("/register", response_class=HTMLResponse)
async def register(
    request: Request,
    email: str = Form(...),
    title: str = Form(...),
    profit_pct: str = Form(...),
    current_price: str = Form(...),
):
    # --- basic validation ---
    def bad(msg: str):
        return _render(request, "register.html", error=msg,
                       email=email, title=title,
                       profit_pct=profit_pct, current_price=current_price)

    if "@" not in email or not email.strip():
        return bad("Please enter a valid email address.")
    if not title.strip():
        return bad("Book title is required.")

    try:
        profit_val = float(profit_pct)
        if not (0 <= profit_val <= 100):
            raise ValueError
    except (ValueError, TypeError):
        return bad("Profit % must be a number between 0 and 100.")

    try:
        price_val = float(current_price)
        if price_val < 0:
            raise ValueError
    except (ValueError, TypeError):
        return bad("Book price must be a non-negative number.")

    # --- ASIN lookup ---
    try:
        _, asin = search_asin(title.strip())
    except ValueError:
        return bad(
            "Could not resolve ASIN for that title. Try a more specific title."
        )
    except Exception as exc:
        log.exception("Unexpected error in search_asin: %s", exc)
        return bad("An error occurred while looking up the book. Please try again.")

    # --- persist (price used as fallback when Amazon page price cannot be scraped) ---
    inserted = repo.register_book(
        {
            "email": email.strip(),
            "title": title.strip(),
            "asin": asin,
            "profit_pct": profit_val,
            "current_price": price_val,
        }
    )

    if not inserted:
        return bad("This book is already being tracked for your account.")

    log.info("Registered book %r (ASIN %s) for %s", title, asin, email)
    return RedirectResponse(
        url=f"/registered?title={title.strip()}",
        status_code=303,
    )


@app.get("/registered", response_class=HTMLResponse)
async def registered(request: Request, title: str = ""):
    return _render(request, "registered.html", title=title)


@app.get("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe(request: Request, email: str = "", asin: str = ""):
    if not email:
        return _render(request, "unsubscribe.html", mode="not_found", email=email)

    if asin:
        updated = repo.unsubscribe_book(email, asin)
        if not updated:
            return _render(request, "unsubscribe.html", mode="not_found", email=email)

        # look up the title for a friendlier message
        title_str = asin
        books = repo.load_active_books()
        for b in books:
            if b.get("asin") == asin:
                title_str = str(b.get("title", asin))
                break

        return _render(request, "unsubscribe.html", mode="book",
                       title=title_str, email=email)
    else:
        count = repo.unsubscribe_email(email)
        if count == 0:
            return _render(request, "unsubscribe.html", mode="not_found", email=email)
        return _render(request, "unsubscribe.html", mode="all",
                       count=count, email=email)
