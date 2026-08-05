"""Test approve/reject (`api/applications.py`) — thiết kế lazy, upsert theo job_id."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.models import Application, Job

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _count(model) -> int:
    async with SessionLocal() as session:
        return (await session.execute(select(func.count()).select_from(model))).scalar_one()


async def _create_job(description: str = "JD bat ky") -> int:
    async with SessionLocal() as session:
        job = Job(description=description)
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job.id


async def test_job_never_touched_shows_pending_in_history(client):
    job_id = await _create_job()

    history = (await client.get("/api/jobs")).json()
    item = next(item for item in history if item["job"]["id"] == job_id)

    assert item["application_status"] == "pending"
    # Thiết kế lazy: KHÔNG có row nào trong applications cho job chưa từng approve/reject.
    assert await _count(Application) == 0


async def test_approve_reflected_in_history(client):
    job_id = await _create_job()

    response = await client.patch(f"/api/jobs/{job_id}/application", json={"status": "approved"})
    assert response.status_code == 200
    assert response.json()["status"] == "approved"

    history = (await client.get("/api/jobs")).json()
    item = next(item for item in history if item["job"]["id"] == job_id)
    assert item["application_status"] == "approved"


async def test_reject_after_approve_updates_same_row_not_a_new_one(client):
    job_id = await _create_job()

    await client.patch(f"/api/jobs/{job_id}/application", json={"status": "approved"})
    assert await _count(Application) == 1

    response = await client.patch(f"/api/jobs/{job_id}/application", json={"status": "rejected"})
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"

    assert await _count(Application) == 1  # update, không tạo row thứ 2


async def test_updated_at_actually_changes_on_second_write(client):
    """Bug đã verify ở prompt Phase 2 mục 1.1: nếu `set_` của upsert quên liệt kê
    `updated_at: func.now()`, cột này đứng yên mãi mãi sau lần ghi đầu — test kiểu chỉ
    check status sẽ không bắt được bug này, phải so sánh updated_at trước/sau.
    """
    job_id = await _create_job()

    first = await client.patch(f"/api/jobs/{job_id}/application", json={"status": "approved"})
    first_updated_at = first.json()["updated_at"]

    await asyncio.sleep(1.1)

    second = await client.patch(f"/api/jobs/{job_id}/application", json={"status": "rejected"})
    second_updated_at = second.json()["updated_at"]

    assert second_updated_at != first_updated_at


async def test_unknown_job_id_returns_404(client):
    response = await client.patch("/api/jobs/999999/application", json={"status": "approved"})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "JOB_NOT_FOUND"
    assert await _count(Application) == 0


@pytest.mark.parametrize("status_value", ["pending", "applied", "amazing", ""])
async def test_disallowed_status_values_rejected_with_422(client, status_value):
    job_id = await _create_job()

    response = await client.patch(f"/api/jobs/{job_id}/application", json={"status": status_value})

    assert response.status_code == 422
    assert await _count(Application) == 0
