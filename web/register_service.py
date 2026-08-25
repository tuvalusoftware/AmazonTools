"""
RegisterService — post-submit background task.

Owns the full lifecycle after a valid registration form is submitted:
ASIN lookup → DB write → email dispatch.
"""

from __future__ import annotations

from urllib.parse import quote

from config import settings
from jobs.email_digest import send_email
from scripts.Search_Asin_Service import SearchAsinService
from utils.logger import get_logger
from utils.registry import BookRepo

log = get_logger(__name__)


def _digest_schedule_label() -> str:
    """Return a human-readable digest schedule derived from settings.

    Parses ``EMAIL_DIGEST_CRON`` (``"<min> <hour> <dom> <mon> <dow>"``) and
    ``TIMEZONE``, producing e.g. "every Monday at 01:00 UTC" or
    "every day at 23:30 Asia/Ho_Chi_Minh".
    """
    _DOW_NAMES = {
        "0": "Sunday", "7": "Sunday",
        "1": "Monday", "2": "Tuesday", "3": "Wednesday",
        "4": "Thursday", "5": "Friday", "6": "Saturday",
    }
    try:
        parts = settings.EMAIL_DIGEST_CRON.split()
        minute, hour, _dom, _mon, dow = parts[:5]
        time_str = f"{int(hour):02d}:{int(minute):02d}"
        tz_label = settings.TIMEZONE or "UTC"
        if dow == "*":
            return f"every day at {time_str} {tz_label}"
        day_name = _DOW_NAMES.get(dow, f"day-{dow}")
        return f"every {day_name} at {time_str} {tz_label}"
    except Exception:  # noqa: BLE001
        return f"on schedule {settings.EMAIL_DIGEST_CRON} ({settings.TIMEZONE})"


class RegisterService:
    """Resolve an ASIN, persist the book, and send the outcome email.

    Parameters
    ----------
    email, title, profit_val:
        Validated values from the registration form.
    """

    def __init__(
        self,
        email: str,
        title: str,
        profit_val: float,
    ) -> None:
        self.email = email
        self.title = title
        self.profit_val = profit_val

    # ------------------------------------------------------------------ #
    # Public entry point                                                   #
    # ------------------------------------------------------------------ #

    def run(self) -> None:
        """Execute the full registration pipeline.

        Runs inside FastAPI's BackgroundTasks thread pool. All errors are
        caught and logged; exceptions must never propagate out of the thread.
        """
        try:
            _, asin = SearchAsinService(self.title).search()
        except (ValueError, RuntimeError) as exc:
            log.warning("ASIN lookup failed for %r: %s", self.title, exc)
            send_email(self.email, *self._email_not_found())
            return
        except Exception as exc:  # noqa: BLE001
            log.warning("Unexpected error in SearchAsinService for %r: %s", self.title, exc)
            send_email(self.email, *self._email_not_found())
            return

        inserted = BookRepo().register_book(
            {
                "email": self.email,
                "title": self.title,
                "asin": asin,
                "profit_pct": self.profit_val,
            }
        )

        if not inserted:
            log.info(
                "Duplicate registration for %r / %s by %s",
                self.title, asin, self.email,
            )
            send_email(self.email, *self._email_duplicate(asin))
            return

        log.info("Registered book %r (ASIN %s) for %s", self.title, asin, self.email)
        send_email(self.email, *self._email_confirmed(asin))

    # ------------------------------------------------------------------ #
    # Email body builders                                                  #
    # ------------------------------------------------------------------ #

    def _email_confirmed(self, asin: str) -> tuple[str, str]:
        unsubscribe_url = (
            f"{settings.WEB_BASE_URL}/unsubscribe"
            f"?email={quote(self.email)}&asin={quote(asin)}"
        )
        subject = f'Your book "{self.title}" has been registered'
        html_body = f"""
<p>Hi,</p>
<p>Your book <strong>{self.title}</strong> (ASIN: <code>{asin}</code>) has been
registered and is now being tracked on Amazon.</p>
<p>You will receive a BSR &amp; price digest email <strong>{_digest_schedule_label()}</strong>.</p>
<p>To stop tracking this book:
<a href="{unsubscribe_url}">unsubscribe</a>.</p>
"""
        return subject, html_body

    def _email_not_found(self) -> tuple[str, str]:
        subject = "We could not find your book on Amazon"
        html_body = f"""
<p>Hi,</p>
<p>We received your registration request for <strong>{self.title}</strong>, but
we were unable to find a matching book on Amazon.</p>
<p>Please double-check the title spelling and
<a href="{settings.WEB_BASE_URL}">try again</a>. For best results, use the exact
title as it appears on Amazon (e.g. "Atomic Habits").</p>
"""
        return subject, html_body

    def _email_duplicate(self, asin: str) -> tuple[str, str]:
        unsubscribe_url = (
            f"{settings.WEB_BASE_URL}/unsubscribe"
            f"?email={quote(self.email)}&asin={quote(asin)}"
        )
        subject = f'You are already tracking "{self.title}"'
        html_body = f"""
<p>Hi,</p>
<p>Good news — you are already tracking <strong>{self.title}</strong>
(ASIN: <code>{asin}</code>). No changes have been made.</p>
<p>To stop tracking:
<a href="{unsubscribe_url}">unsubscribe</a>.</p>
"""
        return subject, html_body
