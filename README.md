# Amazon Review Scraper — Cron Job Tool

A Python cron job that periodically scrapes Amazon product reviews and saves them locally as JSON or CSV.

## Tech stack

| Layer | Library |
|---|---|
| Scheduler | [APScheduler](https://apscheduler.readthedocs.io/) |
| HTTP client | [httpx](https://www.python-httpx.org/) |
| HTML parser | BeautifulSoup4 + lxml |
| Config / env | pydantic-settings |

## Project structure

```
amazon-review-scraper/
├── main.py                  # Entry point — starts the scheduler loop
├── config.py                # All settings (loaded from .env)
├── jobs/
│   └── scrape_reviews.py    # Cron job: fetch → parse → save
├── utils/
│   ├── logger.py            # Rotating file + stdout logger
│   └── storage.py           # JSON / CSV writer
├── data/                    # Output files (auto-created)
├── logs/                    # Log files (auto-created)
├── requirements.txt
└── .env.example
```

## Quick start

```bash
# 1. Clone / enter the project
cd amazon-review-scraper

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure
cp .env.example .env
# Edit .env — set TARGET_ASINS and CRON_SCHEDULE at minimum

# 5. Run
python main.py
```

## Configuration

All options live in `.env` (see `.env.example`).

| Variable | Default | Description |
|---|---|---|
| `CRON_SCHEDULE` | `0 * * * *` | Standard cron expression |
| `TIMEZONE` | `Asia/Ho_Chi_Minh` | Scheduler timezone |
| `TARGET_ASINS` | — | Comma-separated ASIN list |
| `MAX_PAGES` | `5` | Max review pages per ASIN per run |
| `REQUEST_DELAY` | `2.0` | Seconds between requests |
| `OUTPUT_FORMAT` | `json` | `json` or `csv` |
| `PROXY_FILE` | — | Path to a file with one proxy per line |

## Adding a new job

1. Create `jobs/my_new_job.py` with a `run()` function.
2. Register it in `main.py`:

```python
from jobs.my_new_job import run as my_new_job

scheduler.add_job(
    my_new_job,
    trigger=CronTrigger.from_crontab("30 6 * * *"),
    id="my_new_job",
    name="My New Job",
)
```

## Output

Reviews are saved under `data/<ASIN>/<UTC-timestamp>.<json|csv>`.

```json
[
  {
    "asin": "B08N5WRWNW",
    "review_id": "R1ABC123",
    "author": "John D.",
    "rating": 4.0,
    "title": "Great product",
    "body": "Works exactly as described…",
    "date": "Reviewed in the United States on January 1, 2024",
    "verified": true,
    "helpful_votes": 12,
    "scraped_at": "2026-08-06T07:00:00+00:00"
  }
]
```
