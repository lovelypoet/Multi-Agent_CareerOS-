"""Tests for task deduplication, claiming, retries, and worker execution."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from app.core.db import SessionLocal
from app.models.scheduled_task import ScheduledTask
from app.repositories.scheduled_task_repository import ScheduledTaskRepository
from app.worker import run_one_task

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _enqueue(task_type: str = "fetch_jobs", schedule_key: str = "2026-11-08") -> int:
    async with SessionLocal() as session:
        await ScheduledTaskRepository(session).enqueue(
            task_type=task_type,
            schedule_key=schedule_key,
            scheduled_for=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
    async with SessionLocal() as session:
        task = await session.scalar(
            select(ScheduledTask).where(
                ScheduledTask.task_type == task_type,
                ScheduledTask.schedule_key == schedule_key,
            )
        )
        assert task is not None
        return task.id


async def test_enqueue_is_idempotent_for_a_schedule_slot():
    scheduled_for = datetime.now(timezone.utc)
    async with SessionLocal() as session:
        repository = ScheduledTaskRepository(session)
        first = await repository.enqueue(
            task_type="fetch_jobs",
            schedule_key="2026-11-08",
            scheduled_for=scheduled_for,
        )
    async with SessionLocal() as session:
        duplicate = await ScheduledTaskRepository(session).enqueue(
            task_type="fetch_jobs",
            schedule_key="2026-11-08",
            scheduled_for=scheduled_for,
        )

    assert first is True
    assert duplicate is False


async def test_future_task_is_not_claimed():
    async with SessionLocal() as session:
        await ScheduledTaskRepository(session).enqueue(
            task_type="fetch_jobs",
            schedule_key="future",
            scheduled_for=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    async with SessionLocal() as session:
        task = await ScheduledTaskRepository(session).claim_next(
            worker_id="worker-a",
            lease_seconds=120,
        )

    assert task is None


async def test_claimed_task_is_not_claimed_by_another_worker_until_lease_expires():
    await _enqueue()
    async with SessionLocal() as session:
        first_claim = await ScheduledTaskRepository(session).claim_next(
            worker_id="worker-a",
            lease_seconds=120,
        )
    async with SessionLocal() as session:
        second_claim = await ScheduledTaskRepository(session).claim_next(
            worker_id="worker-b",
            lease_seconds=120,
        )

    assert first_claim is not None
    assert first_claim.status == "running"
    assert first_claim.attempts == 1
    assert second_claim is None


async def test_expired_lease_is_reclaimed_and_old_owner_cannot_complete():
    task_id = await _enqueue()
    async with SessionLocal() as session:
        first_claim = await ScheduledTaskRepository(session).claim_next(
            worker_id="worker-a",
            lease_seconds=0,
        )
    async with SessionLocal() as session:
        second_claim = await ScheduledTaskRepository(session).claim_next(
            worker_id="worker-b",
            lease_seconds=120,
        )

    assert first_claim is not None
    assert second_claim is not None
    assert second_claim.id == task_id
    assert second_claim.attempts == 2
    async with SessionLocal() as session:
        assert await ScheduledTaskRepository(session).complete(
            task_id=task_id,
            worker_id="worker-a",
        ) is False
    async with SessionLocal() as session:
        assert await ScheduledTaskRepository(session).complete(
            task_id=task_id,
            worker_id="worker-b",
        ) is True


async def test_expired_lease_after_final_attempt_is_marked_failed():
    task_id = await _enqueue()
    async with SessionLocal() as session:
        await session.execute(
            update(ScheduledTask)
            .where(ScheduledTask.id == task_id)
            .values(max_attempts=1)
        )
        await session.commit()
    async with SessionLocal() as session:
        task = await ScheduledTaskRepository(session).claim_next(
            worker_id="worker-a",
            lease_seconds=0,
        )
    assert task is not None
    async with SessionLocal() as session:
        next_task = await ScheduledTaskRepository(session).claim_next(
            worker_id="worker-b",
            lease_seconds=120,
        )
        failed_task = await session.get(ScheduledTask, task_id)

    assert next_task is None
    assert failed_task is not None
    assert failed_task.status == "failed"
    assert failed_task.last_error == "Worker lease expired after final attempt."


async def test_failure_schedules_retry_then_task_can_succeed():
    task_id = await _enqueue()
    async with SessionLocal() as session:
        task = await ScheduledTaskRepository(session).claim_next(
            worker_id="worker-a",
            lease_seconds=120,
        )
        assert task is not None
        await ScheduledTaskRepository(session).fail(
            task_id=task_id,
            worker_id="worker-a",
            attempts=task.attempts,
            max_attempts=task.max_attempts,
            error="temporary failure",
        )
    async with SessionLocal() as session:
        await session.execute(
            update(ScheduledTask)
            .where(ScheduledTask.id == task_id)
            .values(scheduled_for=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
        await session.commit()
    async with SessionLocal() as session:
        retried = await ScheduledTaskRepository(session).claim_next(
            worker_id="worker-b",
            lease_seconds=120,
        )

    assert retried is not None
    assert retried.id == task_id
    assert retried.attempts == 2
    async with SessionLocal() as session:
        assert await ScheduledTaskRepository(session).complete(
            task_id=task_id,
            worker_id="worker-b",
        ) is True
    async with SessionLocal() as session:
        completed = await session.get(ScheduledTask, task_id)

    assert completed is not None
    assert completed.status == "succeeded"
    assert completed.last_error == "temporary failure"


async def test_worker_executes_and_completes_registered_handler():
    task_id = await _enqueue()
    calls = 0

    async def handler() -> None:
        nonlocal calls
        calls += 1

    assert await run_one_task(
        worker_id="test-worker",
        handlers={"fetch_jobs": handler},
    ) is True

    async with SessionLocal() as session:
        task = await session.get(ScheduledTask, task_id)
    assert calls == 1
    assert task is not None
    assert task.status == "succeeded"


async def test_worker_failure_is_retried():
    task_id = await _enqueue()

    async def handler() -> None:
        raise RuntimeError("expected test failure")

    assert await run_one_task(
        worker_id="test-worker",
        handlers={"fetch_jobs": handler},
    ) is True

    async with SessionLocal() as session:
        task = await session.get(ScheduledTask, task_id)
    assert task is not None
    assert task.status == "queued"
    assert task.attempts == 1
    assert task.last_error == "expected test failure"
