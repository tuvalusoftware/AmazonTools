"""
Interactive manual job runner.

Prompts the user to pick which job(s) to run on demand instead of waiting
for the cron schedule, then runs them.

Usage:
    python -m scripts.run_job
    make run
"""

from __future__ import annotations

from utils.logger import get_logger

log = get_logger(__name__)

_CHOICES = {
    "1": "scrape",
    "2": "digest",
    "3": "both",
}


def _run_scrape() -> None:
    from jobs.scrape_bsr import run as scrape_bsr_run

    log.info("Running scrape_bsr job...")
    scrape_bsr_run()


def _run_digest() -> None:
    from jobs.email_digest import run as email_digest_run

    log.info("Running email_digest job...")
    email_digest_run()


def _prompt_choice() -> str:
    print("Which job do you want to run?")
    print("  1) Scrape BSR/price job (jobs.scrape_bsr)")
    print("  2) Email digest job (jobs.email_digest)")
    print("  3) Both (scrape, then digest)")

    while True:
        raw = input("Choice [1/2/3]: ").strip()
        if raw in _CHOICES:
            return _CHOICES[raw]
        print(f"Invalid choice: {raw!r}. Enter 1, 2, or 3.")


def main() -> None:
    choice = _prompt_choice()

    if choice == "scrape":
        _run_scrape()
    elif choice == "digest":
        _run_digest()
    else:
        _run_scrape()
        _run_digest()


if __name__ == "__main__":
    main()
