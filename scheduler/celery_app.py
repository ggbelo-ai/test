"""Celery application configuration with beat schedule for automated agent runs."""

from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv

load_dotenv()

app = Celery(
    "conviction_engine",
    broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    include=["scheduler.tasks"],
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

# Beat schedule — automated agent triggers
app.conf.beat_schedule = {
    # Daily: Horizon Scanner at 06:00 UTC
    "horizon-scanner-daily": {
        "task": "scheduler.tasks.run_horizon_scanner",
        "schedule": crontab(hour=6, minute=0),
    },
    # Weekly: Founder Radar on Monday at 08:00 UTC
    "founder-radar-weekly": {
        "task": "scheduler.tasks.run_founder_radar",
        "schedule": crontab(hour=8, minute=0, day_of_week=1),
    },
}
