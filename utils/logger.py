"""
Shared logger — logs to stdout and a rotating file under LOG_DIR.
"""

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from config import settings

_configured = False


def _configure() -> None:
    global _configured
    if _configured:
        return

    log_dir = Path(settings.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(settings.LOG_LEVEL.upper())

    # Console handler
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    # Rotating file handler — new file every midnight, keep 14 days
    fh = TimedRotatingFileHandler(
        filename=log_dir / "scraper.log",
        when="midnight",
        backupCount=14,
        encoding="utf-8",
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    _configure()
    return logging.getLogger(name)
