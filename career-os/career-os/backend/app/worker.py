"""Standalone process that polls PostgreSQL and executes queued background work."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy.exc import SQLAlchemyError

from app.core.db import SessionLocal
from app.repositories.scheduled_task_repository import ScheduledTaskRepository
from app.services.scheduling import FETCH_EMAILS_TASK, FETCH_JOBS_TASK

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 5
LEASE_SECONDS = 120
MAX_ATTEMPTS = 3

TaskHandler = Callable[[], Awaitable[None]]


async def _load_handlers() -> dict[str, TaskHandler]:
    from app.workers.fetch_emails import run_fetch_emails
    from app.workers.fetch_jobs import run_fetch_jobs

    return {
        FETCH_JOBS_TASK: run_fetch_jobs,
        FETCH_EMAILS_TASK: run_fetch_emails,
    }


async def _keep_lease(task_id: int, worker_id: str) -> bool:
    interval = max(1, LEASE_SECONDS // 3)
    while True:
        await asyncio.sleep(interval)
        async with SessionLocal() as session:
            try:
                renewed = await ScheduledTaskRepository(session).renew_lease(
                    task_id=task_id,
                    worker_id=worker_id,
                    lease_seconds=LEASE_SECONDS,
                )
            except SQLAlchemyError:
                logger.exception("Could not renew lease for scheduled task %s.", task_id)
                return False
        if not renewed:
            return False


async def run_one_task(
    *,
    worker_id: str | None = None,
    handlers: dict[str, TaskHandler] | None = None,
) -> bool:
    """Claim and execute a single due task; return False when the queue has no work."""
    worker_id = worker_id or str(uuid.uuid4())
    handlers = handlers or await _load_handlers()
    async with SessionLocal() as session:
        task = await ScheduledTaskRepository(session).claim_next(
            worker_id=worker_id,
            lease_seconds=LEASE_SECONDS,
        )
    if task is None:
        return False

    handler = handlers.get(task.task_type)
    lease: asyncio.Task[bool] | None = None
    try:
        if handler is None:
            raise ValueError(f"Unknown scheduled task type: {task.task_type}")

        execution = asyncio.create_task(handler())
        lease = asyncio.create_task(_keep_lease(task.id, worker_id))
        done, _ = await asyncio.wait(
            {execution, lease},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if lease in done and not lease.result():
            execution.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await execution
            logger.error("Lost lease for scheduled task %s; cancelled its handler.", task.id)
            return True

        await execution
    except Exception as exc:
        logger.exception("Scheduled task %s (%s) failed.", task.id, task.task_type)
        async with SessionLocal() as session:
            await ScheduledTaskRepository(session).fail(
                task_id=task.id,
                worker_id=worker_id,
                attempts=task.attempts,
                max_attempts=task.max_attempts or MAX_ATTEMPTS,
                error=str(exc),
            )
    else:
        async with SessionLocal() as session:
            completed = await ScheduledTaskRepository(session).complete(
                task_id=task.id,
                worker_id=worker_id,
            )
        if not completed:
            logger.warning("Task %s finished after this worker lost its lease.", task.id)
    finally:
        if lease is not None and not lease.done():
            lease.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await lease
    return True


async def run_worker() -> None:
    worker_id = str(uuid.uuid4())
    handlers = await _load_handlers()
    logger.info("Background worker started with id %s.", worker_id)
    while True:
        processed = await run_one_task(worker_id=worker_id, handlers=handlers)
        if not processed:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
