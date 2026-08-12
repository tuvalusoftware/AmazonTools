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

from pathlib import Path

from playwright.sync_api import BrowserContext, Page, sync_playwright

from config import settings
from utils.logger import get_logger

log = get_logger(__name__)

_SIGNIN_URL = "https://www.amazon.com/gp/sign-in.html"


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

def _page_needs_login(page: Page) -> bool:
    url = page.url.lower()
    return "ap/signin" in url or "gp/sign-in" in url


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
        email_el.fill(email)
        page.locator("#continue, input[type='submit']").first.click()

        # --- password step ---
        pwd_el = page.wait_for_selector(
            "#ap_password, input[name='password']", timeout=15_000
        )
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
                email_el.fill(email)
                page.locator("#continue, input[type='submit']").first.click()

                pwd_el = page.wait_for_selector(
                    "#ap_password, input[name='password']", timeout=15_000
                )
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


def fetch_page_html(url: str) -> str | None:
    """
    Return the fully-rendered HTML of *url* using a Playwright browser that
    carries the saved Amazon session.

    Flow:
      1. Load cookies from BROWSER_STATE_PATH (if the file exists).
      2. Navigate to *url*.
      3. If Amazon redirects to sign-in, auto-login and retry.
      4. Persist the (possibly refreshed) session back to disk.
      5. Return page HTML, or None on unrecoverable error.
    """
    state_path = Path(settings.BROWSER_STATE_PATH)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=settings.BROWSER_HEADLESS)

        ctx_opts: dict = {}
        if state_path.exists():
            ctx_opts["storage_state"] = str(state_path)
            log.debug("Loaded browser state from %s", state_path)

        context: BrowserContext = browser.new_context(**ctx_opts)
        page: Page = context.new_page()

        try:
            page.goto(url, wait_until="networkidle", timeout=30_000)
        except Exception as exc:
            log.warning("fetch_page_html: navigation failed for %s — %s", url, exc)
            browser.close()
            return None

        # Detect login wall
        if _page_needs_login(page) or not _is_logged_in(page):
            log.info("Session missing or expired for %s — attempting auto-login …", url)
            ok = _do_login(page)
            if not ok:
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
        _save_state(context)
        browser.close()
        return html
