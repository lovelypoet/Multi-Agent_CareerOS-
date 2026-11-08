"""Scheduler callbacks enqueue work; they never run crawlers or AI agents themselves."""

from __future__ import annotations

from datetime import datetime

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.repositories.scheduled_task_repository import ScheduledTaskRepository

FETCH_JOBS_TASK = "fetch_jobs"
FETCH_EMAILS_TASK = "fetch_emails"


async def _enqueue(task_type: str, schedule_key: str) -> None:
    now = datetime.now().astimezone()
    async with SessionLocal() as session:
        await ScheduledTaskRepository(session).enqueue(
            task_type=task_type,
            schedule_key=schedule_key,
            scheduled_for=now,
        )


async def enqueue_fetch_jobs() -> None:
    """Queue at most one job-discovery run per local calendar day."""
    await _enqueue(FETCH_JOBS_TASK, datetime.now().astimezone().date().isoformat())


async def enqueue_fetch_emails() -> None:
    """Queue at most one email scan per configured interval slot."""
    interval_hours = get_settings().gmail_fetch_interval_hours
    now = datetime.now().astimezone()
    slot_hour = now.hour - now.hour % interval_hours
    slot = now.replace(hour=slot_hour, minute=0, second=0, microsecond=0)
    await _enqueue(FETCH_EMAILS_TASK, slot.isoformat())
