# 5. Wire the job into the scheduler, config, and manual runner

## `config.py`

Add a new cron setting next to `EMAIL_DIGEST_CRON` (`config.py:83`):

```python
MONTHLY_SUMMARY_CRON: str = "5 0 1 * *"   # 1st of month, 00:05 (interpret against TIMEZONE)
```

00:05 rather than 00:00 to comfortably clear midnight before the previous
day's final `scrape_bsr` run (currently `0 23 * * *`, 23:00) has finished
writing its snapshot rows — mirrors the existing gap between
`SCRAPE_BSR_CRON` (23:00 daily) and `EMAIL_DIGEST_CRON` (01:00 Monday).

## `.env` / `.env.example`

Add alongside `EMAIL_DIGEST_CRON`:

```
MONTHLY_SUMMARY_CRON=5 0 1 * *
```

## `main.py`

Register the new job the same way `email_digest_run` is registered
(`main.py:64-71`):

```python
from jobs.monthly_summary import run as monthly_summary_run

scheduler.add_job(
    monthly_summary_run,
    trigger=CronTrigger.from_crontab(settings.MONTHLY_SUMMARY_CRON, timezone=settings.TIMEZONE),
    id="monthly_summary",
    name="Compute Monthly Profit Summary",
    replace_existing=True,
    misfire_grace_time=3600,
)
log.info("monthly_summary job registered")
```

`misfire_grace_time=3600` (1 hour) rather than the digest job's 300s —
this job only needs to run once and has no time-sensitive delivery like an
email, so a wider recovery window if the process was down at the exact
trigger time is harmless.

## `scripts/run_job.py`

Add a 4th on-demand choice so this can be smoke-tested manually without
waiting for the 1st of the month (matches the "Manual test" checklist in
`main.md`):

```python
_CHOICES = {
    "1": "scrape",
    "2": "digest",
    "3": "both",
    "4": "monthly_summary",
}

def _run_monthly_summary() -> None:
    from jobs.monthly_summary import run as monthly_summary_run

    log.info("Running monthly_summary job...")
    monthly_summary_run()
```

Update `_prompt_choice()`'s printed menu and `main()`'s dispatch to cover
the new option 4.

## Test coverage

- `tests/test_web_app.py` or a new scheduler-focused test isn't strictly
  necessary — `main.py`'s scheduler wiring for `email_digest` doesn't
  appear to have a dedicated unit test today either (job registration is
  thin glue). Skip a dedicated test for the `main.py` change; verify
  manually that `python main.py` starts without error and logs
  `monthly_summary job registered`.
- `scripts/run_job.py`'s new dispatch branch can be covered by a small
  test if `tests/` already has coverage for the existing 3 choices —
  check for a `test_run_job.py` first; if one exists, add the 4th-choice
  case there for consistency, otherwise skip (this script had no prior
  test coverage to begin with).
