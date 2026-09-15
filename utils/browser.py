"""
Playwright-based browser session manager.

Responsibilities:
- Load saved cookies from BROWSER_STATE_PATH (if exists).
- Detect when Amazon redirects to the sign-in page.
- Auto-login using AMAZON_EMAIL / AMAZON_PASSWORD from .env.
- Handle the OTP / "verify your identity" step gracefully (logs a warning,
  waits up to 60 s for the user to complete it manually if the browser is
  running in non-headless mode).
- Persist the updated session back to BROWSER_STATE_PATH after every fetch.
- Return the fully-rendered HTML string so SmartScraperGraph can parse it
  without launching its own browser (and without auth cookies).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import BrowserContext, Page, sync_playwright

from config import settings
from utils.email_sender import send_email
from utils.logger import get_logger

log = get_logger(__name__)

_SIGNIN_URL = "https://www.amazon.com/gp/sign-in.html"

# Don't send more than one session-expired alert within this window — a
# single scrape run can hit every failing ASIN/retry and would otherwise
# flood the inbox.
_ALERT_THROTTLE_HOURS = 12
_ALERT_MARKER_PATH = "data/.session_alert_last_sent"


def _notify_session_expired() -> None:
    """Email AMAZON_EMAIL that the saved session needs a fresh `make login`.

    Called when auto-login fails (Amazon is demanding OTP/CAPTCHA/device
    approval that can't be completed headlessly), which is the concrete
    signal that browser_state.json is dead — not the cookie expiry dates,
    which are far in the future and not the actual failure mode.
    """
    marker = Path(_ALERT_MARKER_PATH)
    now = datetime.now(timezone.utc)
    if marker.exists():
        try:
            last = datetime.fromisoformat(marker.read_text().strip())
            if now - last < timedelta(hours=_ALERT_THROTTLE_HOURS):
                return
        except Exception:
            pass

    to = settings.AMAZON_EMAIL
    if not to:
        log.warning("Cannot send session-expired alert — AMAZON_EMAIL not set")
        return

    try:
        send_email(
            to=to,
            subject="[BSR Tracker] Amazon session expired — re-login required",
            html_body=(
                "<p>The saved Amazon browser session "
                "(<code>data/browser_state.json</code>) is no longer valid. "
                "Amazon is requiring additional verification (OTP / CAPTCHA / "
                "device approval) that the scraper cannot complete automatically.</p>"
                "<p>Please run <code>make login</code> and redeploy the refreshed "
                "<code>browser_state.json</code> to the server.</p>"
            ),
        )
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(now.isoformat())
        log.info("Session-expired alert email sent to %s", to)
    except Exception as exc:
        log.error("Failed to send session-expired alert: %s", exc)


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

def _page_needs_login(page: Page) -> bool:
    url = page.url.lower()
    return "ap/signin" in url or "gp/sign-in" in url


def _page_is_captcha(page: Page) -> bool:
    """Return True when Amazon is showing a robot/CAPTCHA challenge page."""
    url = page.url.lower()
    if "validatecaptcha" in url or "captcha" in url:
        return True
    try:
        content = page.content()
        # Both the image-captcha and the "Sorry, we just need to make sure you're not a robot" interstitial
        return (
            "Type the characters you see in this image" in content
            or "Enter the characters you see below" in content
            or "robot" in content.lower()
            and "captcha" in content.lower()
        )
    except Exception:
        return False


def _is_logged_in(page: Page) -> bool:
    """Return True when the Amazon nav bar shows an account name."""
    try:
        text = page.locator("#nav-link-accountList").inner_text(timeout=4_000)
        return "sign in" not in text.lower()
    except Exception:
        return False


def _do_login(page: Page) -> bool:
    """
    Auto-fill email + password and submit.

    Returns True if login is confirmed successful.
    Amazon may still show a CAPTCHA or OTP page — in that case we log a
    warning and (in non-headless mode) wait up to 60 s for manual completion.
    """
    email = settings.AMAZON_EMAIL
    password = settings.AMAZON_PASSWORD

    if not email or not password:
        log.error(
            "Auto-login failed: AMAZON_EMAIL / AMAZON_PASSWORD not set in .env"
        )
        return False

    log.info("Auto-login: navigating to Amazon sign-in …")
    try:
        page.goto(_SIGNIN_URL, wait_until="domcontentloaded", timeout=20_000)
        page.wait_for_url("**/ap/signin**", timeout=15_000)

        # --- email step ---
        email_el = page.wait_for_selector(
            "#ap_email, input[name='email']", timeout=15_000
        )
        assert email_el is not None
        email_el.fill(email)
        page.locator("#continue, input[type='submit']").first.click()

        # --- password step ---
        pwd_el = page.wait_for_selector(
            "#ap_password, input[name='password']", timeout=15_000
        )
        assert pwd_el is not None
        pwd_el.fill(password)
        page.locator("#signInSubmit, input[type='submit']").first.click()

        page.wait_for_load_state("networkidle", timeout=20_000)
    except Exception as exc:
        log.warning("Auto-login: navigation error — %s", exc)
        return False

    if _is_logged_in(page):
        log.info("Auto-login: success")
        return True

    # Could be OTP, CAPTCHA, or "approve this device" page
    log.warning(
        "Auto-login: Amazon is showing an extra verification step "
        "(OTP / CAPTCHA / device approval). "
        "Set BROWSER_HEADLESS=false and complete it manually, "
        "or pre-save a session with `make login`."
    )

    if not settings.BROWSER_HEADLESS:
        log.info("Waiting up to 60 s for manual verification …")
        try:
            # Wait until the nav account link no longer says "Sign in"
            page.wait_for_function(
                "!document.querySelector('#nav-link-accountList')"
                "?.innerText.toLowerCase().includes('sign in')",
                timeout=60_000,
            )
            if _is_logged_in(page):
                log.info("Manual verification completed.")
                return True
        except Exception:
            pass

    return False


def _save_state(context: BrowserContext) -> None:
    state_path = Path(settings.BROWSER_STATE_PATH)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(state_path))
    log.debug("Browser state saved → %s", state_path)


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #

def login_session() -> bool:
    """
    Open a visible browser, navigate to the Amazon sign-in page, attempt
    auto-login, then wait for the user to complete any OTP / CAPTCHA step.
    Saves the authenticated session to BROWSER_STATE_PATH and returns True
    on success.

    Always runs with headless=False so the user can see what is happening.
    """
    state_path = Path(settings.BROWSER_STATE_PATH)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context: BrowserContext = browser.new_context()
        page: Page = context.new_page()

        log.info("Opening Amazon sign-in page …")
        try:
            page.goto(_SIGNIN_URL, wait_until="domcontentloaded", timeout=20_000)
            # /gp/sign-in.html redirects to /ap/signin — wait for redirect to settle
            page.wait_for_url("**/ap/signin**", timeout=15_000)
        except Exception as exc:
            log.error("Failed to open sign-in page: %s", exc)
            browser.close()
            return False

        # Auto-fill credentials if provided
        email = settings.AMAZON_EMAIL
        password = settings.AMAZON_PASSWORD

        if email and password:
            try:
                email_el = page.wait_for_selector(
                    "#ap_email, input[name='email']", timeout=15_000
                )
                assert email_el is not None
                email_el.fill(email)
                page.locator("#continue, input[type='submit']").first.click()

                pwd_el = page.wait_for_selector(
                    "#ap_password, input[name='password']", timeout=15_000
                )
                assert pwd_el is not None
                pwd_el.fill(password)
                page.locator("#signInSubmit, input[type='submit']").first.click()
                page.wait_for_load_state("networkidle", timeout=20_000)
            except Exception as exc:
                log.warning("Auto-fill failed: %s", exc)

        # If already logged in, save and done
        if _is_logged_in(page):
            log.info("Logged in successfully.")
            _save_state(context)
            browser.close()
            return True

        # Prompt user to finish OTP / CAPTCHA manually — wait up to 120 s
        log.warning(
            "Amazon requires additional verification (OTP / CAPTCHA / device approval). "
            "Please complete it in the browser window. Waiting up to 120 s …"
        )
        try:
            page.wait_for_function(
                "!document.querySelector('#nav-link-accountList')"
                "?.innerText.toLowerCase().includes('sign in')",
                timeout=120_000,
            )
        except Exception:
            pass

        if _is_logged_in(page):
            log.info("Login completed after manual verification.")
            _save_state(context)
            browser.close()
            return True

        log.error("Login failed — session was NOT saved.")
        browser.close()
        return False


def _save_captcha_screenshot(page: Page, url: str) -> None:
    """Save a full-page screenshot when a CAPTCHA is detected.

    Files are written to ``data/captcha/`` as
    ``captcha_<YYYYMMDD_HHMMSS>_<slug>.png``.  The directory is created
    automatically.  Any error during saving is logged but never raised so
    that the CAPTCHA-handling flow is never interrupted.
    """
    import re as _re
    from datetime import datetime as _dt

    try:
        out_dir = Path(settings.OUTPUT_DIR) / "captcha"
        out_dir.mkdir(parents=True, exist_ok=True)

        timestamp = _dt.now().strftime("%Y%m%d_%H%M%S")
        slug = _re.sub(r"[^a-zA-Z0-9]", "_", url)[-40:]
        filename = f"captcha_{timestamp}_{slug}.png"
        path = out_dir / filename

        page.screenshot(path=str(path), full_page=True)
        log.warning("fetch_page_html: CAPTCHA screenshot saved → %s", path)
    except Exception as exc:
        log.debug("fetch_page_html: failed to save CAPTCHA screenshot — %s", exc)


def _save_debug_screenshot(page: Page, url: str, label: str = "debug") -> None:
    """Save a full-page screenshot to ``data/debug/`` for diagnosis.

    Files are named ``<label>_<YYYYMMDD_HHMMSS>_<slug>.png``.
    Errors are logged at DEBUG level and never raised.
    """
    import re as _re
    from datetime import datetime as _dt

    try:
        out_dir = Path(settings.OUTPUT_DIR) / "debug"
        out_dir.mkdir(parents=True, exist_ok=True)

        timestamp = _dt.now().strftime("%Y%m%d_%H%M%S")
        slug = _re.sub(r"[^a-zA-Z0-9]", "_", url)[-40:]
        filename = f"{label}_{timestamp}_{slug}.png"
        path = out_dir / filename

        page.screenshot(path=str(path), full_page=True)
        log.warning("fetch_page_html: debug screenshot saved → %s", path)
    except Exception as exc:
        log.debug("fetch_page_html: failed to save debug screenshot — %s", exc)


def extract_bsr_html_fragment(html: str) -> str:
    """Return the smallest HTML snippet that contains BSR + price data.

    Strategy (tried in order, first match wins):
    1. ``#detailBullets_feature_div`` — compact bullet-list block for most books.
    2. ``#audibleProductDetails`` — Audible audiobook product detail table.
    3. ``#productDetails_detailBullets_sections1`` — table-style variant for
       physical/Kindle books.
    4. Full HTML as fallback so the caller is never left with an empty string.

    The fragment is typically 5–30 KB instead of the 300–600 KB full-page HTML,
    which dramatically reduces LLM token usage and improves extraction accuracy.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    for selector in (
        "#detailBullets_feature_div",
        "#audibleProductDetails",
        "#productDetails_detailBullets_sections1",
    ):
        node = soup.select_one(selector)
        if node:
            fragment = str(node)
            log.debug(
                "extract_bsr_html_fragment: using selector %r → %d chars",
                selector,
                len(fragment),
            )
            return fragment

    log.debug("extract_bsr_html_fragment: no known selector matched — returning full HTML")
    return html


def extract_price_from_html(html: str) -> float:
    """Parse the current Kindle/book price directly from the page HTML.

    Tries several stable DOM patterns in order of specificity so it works
    across Amazon's different buybox layouts (Kindle, paperback, hardcover):

    1. ``[data-pricetopay-label]`` attribute — the canonical "price to pay"
       element Amazon uses for its unified buybox.  The aria-label always
       contains the dollar amount (e.g. ``"$14.99 with 50 percent savings"``).
    2. ``span.apex-pricetopay-value[aria-label]`` — same data, CSS fallback.
    3. ``span.ebook-price-value[aria-label]`` — older Kindle swatch price span.
    4. ``span#price[aria-label]``, ``span#kindle-price[aria-label]`` — legacy
       price block selectors still used on some book pages.
    5. ``span.a-price:has(.a-price-whole)`` text — last-resort fallback that
       reads the visible price digits directly from the DOM.

    Returns 0.0 when no price can be found.
    """
    import re as _re
    from bs4 import BeautifulSoup

    _DOLLAR_RE = _re.compile(r"\$\s*([\d,]+\.?\d*)")

    def _parse_dollar(text: str) -> float:
        m = _DOLLAR_RE.search(text)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except ValueError:
                pass
        return 0.0

    soup = BeautifulSoup(html, "html.parser")

    # 1. data-pricetopay-label — most reliable on modern Amazon pages
    node = soup.find(attrs={"data-pricetopay-label": True})  # type: ignore[call-overload]
    if node:
        label = str(node.get("aria-label") or "")
        price = _parse_dollar(label)
        if price:
            log.debug("extract_price_from_html: found via data-pricetopay-label → $%.2f", price)
            return price

    # 2 & 3 — CSS class selectors with aria-label
    for css in (
        "span.apex-pricetopay-value",
        "span.ebook-price-value",
        "span#price",
        "span#kindle-price",
    ):
        node = soup.select_one(css)
        if node:
            label = str(node.get("aria-label") or node.get_text())
            price = _parse_dollar(label)
            if price:
                log.debug("extract_price_from_html: found via %r → $%.2f", css, price)
                return price

    # 4. Last-resort: read visible price digits from first .a-price block
    price_node = soup.select_one("span.a-price")
    if price_node:
        whole = price_node.select_one(".a-price-whole")
        frac = price_node.select_one(".a-price-fraction")
        if whole:
            try:
                price = float(f"{whole.get_text().strip('.').strip()}.{frac.get_text().strip() if frac else '00'}")
                if price:
                    log.debug("extract_price_from_html: found via .a-price text → $%.2f", price)
                    return price
            except ValueError:
                pass

    log.debug("extract_price_from_html: no price found")
    return 0.0


def fetch_page_html(
    url: str,
    *,
    retries: int = 2,
    retry_delay: float = 3.0,
) -> str | None:
    """
    Return the fully-rendered HTML of *url* using a Playwright browser that
    carries the saved Amazon session.

    Flow:
      1. Load cookies from BROWSER_STATE_PATH (if the file exists).
      2. Navigate to *url* (retried up to *retries* times on timeout/error).
      3. If Amazon redirects to sign-in, auto-login and retry.
      4. Persist the (possibly refreshed) session back to disk.
      5. Return page HTML, or None on unrecoverable error.

    Parameters
    ----------
    retries:
        Number of additional attempts after the first failure (default 2,
        so up to 3 total attempts).
    retry_delay:
        Seconds to wait between attempts (default 3.0).
    """
    import time

    state_path = Path(settings.BROWSER_STATE_PATH)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=settings.BROWSER_HEADLESS)

        ctx_opts: dict[str, Any] = {}
        if state_path.exists():
            ctx_opts["storage_state"] = str(state_path)
            log.debug("Loaded browser state from %s", state_path)

        context: BrowserContext = browser.new_context(**ctx_opts)
        page: Page = context.new_page()

        last_exc: Exception | None = None
        for attempt in range(1 + retries):
            try:
                page.goto(url, wait_until="networkidle", timeout=30_000)
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
                log.warning(
                    "fetch_page_html: navigation failed for %s (attempt %d/%d) — %s",
                    url,
                    attempt + 1,
                    1 + retries,
                    exc,
                )
                if attempt < retries:
                    time.sleep(retry_delay)

        if last_exc is not None:
            browser.close()
            return None

        # Detect login wall
        if _page_needs_login(page) or not _is_logged_in(page):
            log.info("Session missing or expired for %s — attempting auto-login …", url)
            ok = _do_login(page)
            if not ok:
                _notify_session_expired()
                _save_state(context)
                browser.close()
                return None

            # Re-navigate to the original review URL
            try:
                page.goto(url, wait_until="networkidle", timeout=30_000)
            except Exception as exc:
                log.warning("fetch_page_html: re-navigation failed — %s", exc)
                _save_state(context)
                browser.close()
                return None

        html: str = page.content()

        # Detect CAPTCHA / robot-check interstitial — screenshot for inspection,
        # then return None so the caller can retry instead of feeding a useless
        # page to the LLM.
        if _page_is_captcha(page):
            _save_captcha_screenshot(page, url)
            log.warning(
                "fetch_page_html: Amazon served a CAPTCHA page for %s — "
                "session may be rate-limited; returning None",
                url,
            )
            _save_state(context)
            browser.close()
            return None

        _save_state(context)
        browser.close()
        return html
