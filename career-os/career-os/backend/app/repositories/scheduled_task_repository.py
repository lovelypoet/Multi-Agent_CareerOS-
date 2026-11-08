"""Persistence operations for the PostgreSQL-backed scheduled task queue."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scheduled_task import ScheduledTask

MAX_ERROR_CHARS = 4000


class ScheduledTaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def enqueue(
        self,
        *,
        task_type: str,
        schedule_key: str,
        scheduled_for: datetime,
        payload: dict | None = None,
    ) -> bool:
        statement = (
            insert(ScheduledTask)
            .values(
                task_type=task_type,
                schedule_key=schedule_key,
                scheduled_for=scheduled_for,
                payload=payload or {},
                status="queued",
            )
            .on_conflict_do_nothing(constraint="uq_scheduled_tasks_type_schedule")
            .returning(ScheduledTask.id)
        )
        task_id = await self.session.scalar(statement)
        await self.session.commit()
        return task_id is not None

    async def claim_next(
        self,
        *,
        worker_id: str,
        lease_seconds: int,
    ) -> ScheduledTask | None:
        now = datetime.now(timezone.utc)
        await self.session.execute(
            update(ScheduledTask)
            .where(
                ScheduledTask.status == "running",
                ScheduledTask.lease_expires_at <= now,
                ScheduledTask.attempts >= ScheduledTask.max_attempts,
            )
            .values(
                status="failed",
                completed_at=now,
                locked_by=None,
                lease_expires_at=None,
                last_error="Worker lease expired after final attempt.",
                updated_at=now,
            )
        )
        statement = (
            select(ScheduledTask)
            .where(
                ScheduledTask.attempts < ScheduledTask.max_attempts,
                or_(
                    and_(ScheduledTask.status == "queued", ScheduledTask.scheduled_for <= now),
                    and_(
                        ScheduledTask.status == "running",
                        ScheduledTask.lease_expires_at <= now,
                    ),
                ),
            )
            .order_by(ScheduledTask.scheduled_for, ScheduledTask.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        task = await self.session.scalar(statement)
        if task is None:
            await self.session.commit()
            return None

        task.status = "running"
        task.attempts += 1
        task.started_at = now
        task.completed_at = None
        task.locked_by = worker_id
        task.lease_expires_at = now + timedelta(seconds=lease_seconds)
        task.updated_at = now
        await self.session.commit()
        return task

    async def renew_lease(self, *, task_id: int, worker_id: str, lease_seconds: int) -> bool:
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            update(ScheduledTask)
            .where(
                ScheduledTask.id == task_id,
                ScheduledTask.status == "running",
                ScheduledTask.locked_by == worker_id,
            )
            .values(
                lease_expires_at=now + timedelta(seconds=lease_seconds),
                updated_at=now,
            )
        )
        await self.session.commit()
        return result.rowcount == 1

    async def complete(self, *, task_id: int, worker_id: str) -> bool:
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            update(ScheduledTask)
            .where(
                ScheduledTask.id == task_id,
                ScheduledTask.status == "running",
                ScheduledTask.locked_by == worker_id,
            )
            .values(
                status="succeeded",
                completed_at=now,
                locked_by=None,
                lease_expires_at=None,
                updated_at=now,
            )
        )
        await self.session.commit()
        return result.rowcount == 1

    async def fail(
        self,
        *,
        task_id: int,
        worker_id: str,
        attempts: int,
        max_attempts: int,
        error: str,
    ) -> bool:
        now = datetime.now(timezone.utc)
        is_final_attempt = attempts >= max_attempts
        delay_seconds = min(300, 30 * (2 ** max(0, attempts - 1)))
        result = await self.session.execute(
            update(ScheduledTask)
            .where(
                ScheduledTask.id == task_id,
                ScheduledTask.status == "running",
                ScheduledTask.locked_by == worker_id,
            )
            .values(
                status="failed" if is_final_attempt else "queued",
                scheduled_for=now + timedelta(seconds=delay_seconds),
                completed_at=now if is_final_attempt else None,
                locked_by=None,
                lease_expires_at=None,
                last_error=error[:MAX_ERROR_CHARS],
                updated_at=now,
            )
        )
        await self.session.commit()
        return result.rowcount == 1
