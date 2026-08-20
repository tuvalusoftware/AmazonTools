"""
Entry point — starts the APScheduler cron loop and the FastAPI web UI.

Usage:
    python main.py
"""

import signal
import sys
import threading
import time

import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config import settings
from jobs.email_digest import run as email_digest_run
from jobs.monthly_summary import run as monthly_summary_run
from jobs.scrape_bsr import run as scrape_bsr_job
from utils.logger import get_logger
from utils.registry import BookRepo
from web.app import app as web_app

log = get_logger(__name__)


def _shutdown(scheduler: BackgroundScheduler, sig, frame) -> None:
    log.info("Shutdown signal received (%s). Stopping scheduler…", sig)
    scheduler.shutdown(wait=False)
    sys.exit(0)


def _start_web_server() -> None:
    """Run the FastAPI app in a daemon thread so it doesn't block the scheduler."""
    log.info("Web UI available at http://localhost:%d", settings.WEB_PORT)
    uvicorn.run(
        web_app,
        host="0.0.0.0",
        port=settings.WEB_PORT,
        log_level="warning",
    )


def main() -> None:
    BookRepo().init_db()
    log.info("SQLite registry initialised at %s", settings.DB_PATH)

    web_thread = threading.Thread(target=_start_web_server, daemon=True, name="web-ui")
    web_thread.start()

    log.info("Starting Amazon BSR Scraper — cron tool")

    scheduler = BackgroundScheduler(timezone=settings.TIMEZONE)

    scheduler.add_job(
        scrape_bsr_job,
        trigger=CronTrigger.from_crontab(settings.SCRAPE_BSR_CRON, timezone=settings.TIMEZONE),
        id="scrape_bsr",
        name="Scrape Amazon Best Seller Rank",
        replace_existing=True,
        misfire_grace_time=60,
    )

    scheduler.add_job(
        email_digest_run,
        trigger=CronTrigger.from_crontab(settings.EMAIL_DIGEST_CRON, timezone=settings.TIMEZONE),
        id="email_digest",
        name="Send Weekly BSR Digest Email",
        replace_existing=True,
        misfire_grace_time=300,
    )
    log.info("email_digest job registered")

    scheduler.add_job(
        monthly_summary_run,
        trigger=CronTrigger.from_crontab(settings.MONTHLY_SUMMARY_CRON, timezone=settings.TIMEZONE),
        id="monthly_summary",
        name="Compute Monthly Profit Summary",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    log.info("monthly_summary job registered")

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda s, f: _shutdown(scheduler, s, f))

    scheduler.start()
    scrape_job = scheduler.get_job("scrape_bsr")
    log.info("Scheduler started. Next run: %s", scrape_job.next_run_time if scrape_job else "unknown")

    try:
        while True:
            time.sleep(30)
    except (KeyboardInterrupt, SystemExit):
        _shutdown(scheduler, None, None)


if __name__ == "__main__":
    main()
