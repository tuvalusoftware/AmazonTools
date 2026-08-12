"""
Entry point — starts the APScheduler cron loop.

Usage:
    python main.py
"""

import signal
import sys
import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config import settings
from jobs.scrape_bsr import run as scrape_bsr_job
from utils.logger import get_logger

log = get_logger(__name__)


def _shutdown(scheduler: BackgroundScheduler, sig, frame) -> None:
    log.info("Shutdown signal received (%s). Stopping scheduler…", sig)
    scheduler.shutdown(wait=False)
    sys.exit(0)


def main() -> None:
    log.info("Starting Amazon BSR Scraper — cron tool")

    scheduler = BackgroundScheduler(timezone=settings.TIMEZONE)

    scheduler.add_job(
        scrape_bsr_job,
        trigger=CronTrigger.from_crontab(settings.CRON_SCHEDULE, timezone=settings.TIMEZONE),
        id="scrape_bsr",
        name="Scrape Amazon Best Seller Rank",
        replace_existing=True,
        misfire_grace_time=60,
    )

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda s, f: _shutdown(scheduler, s, f))

    scheduler.start()
    log.info("Scheduler started. Next run: %s", scheduler.get_job("scrape_bsr").next_run_time)

    try:
        while True:
            time.sleep(30)
    except (KeyboardInterrupt, SystemExit):
        _shutdown(scheduler, None, None)


if __name__ == "__main__":
    main()
