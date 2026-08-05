"""Test `GET /api/dashboard/summary` — 3 con số theo đúng logic đã chốt ở prompt Phase 2 mục 1.3.

DB được truncate trước mỗi test (autouse fixture trong conftest.py), nên assert bằng số
tuyệt đối là an toàn, không cần lo dữ liệu từ test khác lẫn vào.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.core.db import SessionLocal
from app.models import Application, Job, MatchResult, Resume

pytestmark = pytest.mark.asyncio(loop_scope="session")

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
UTC = ZoneInfo("UTC")


async def test_jobs_today_counts_job_created_at_vietnam_early_morning(client):
    """Chỗ dễ sai nhất: VN 00:00-07:00 luôn rơi vào NGÀY UTC TRƯỚC ĐÓ (VN = UTC+7) — nếu
    query dùng nhầm ngày UTC thay vì ngày VN, job này sẽ bị tính là "hôm qua" một cách âm
    thầm dù thực tế vừa được tạo sáng sớm hôm nay theo giờ VN.
    """
    now_vn = datetime.now(VN_TZ)
    vn_midnight_today = now_vn.replace(hour=0, minute=0, second=0, microsecond=0)
    boundary_created_at = (vn_midnight_today + timedelta(minutes=30)).astimezone(UTC)

    async with SessionLocal() as session:
        session.add(Job(description="Job luc rang sang gio VN", created_at=boundary_created_at))
        await session.commit()

    summary = (await client.get("/api/dashboard/summary")).json()
    assert summary["jobs_today"] == 1


async def test_jobs_today_excludes_jobs_from_other_days(client):
    two_days_ago = datetime.now(UTC) - timedelta(days=2)
    async with SessionLocal() as session:
        session.add(Job(description="Job tu 2 ngay truoc", created_at=two_days_ago))
        await session.commit()

    summary = (await client.get("/api/dashboard/summary")).json()
    assert summary["jobs_today"] == 0


async def test_approved_count_is_cumulative_not_filtered_by_day(client):
    """Đã chốt: approved_count là tổng lũy kế, KHÔNG lọc theo ngày."""
    old_ts = datetime.now(UTC) - timedelta(days=10)
    async with SessionLocal() as session:
        job = Job(description="Job da approve tu 10 ngay truoc")
        session.add(job)
        await session.flush()
        session.add(Application(job_id=job.id, status="approved", created_at=old_ts, updated_at=old_ts))
        await session.commit()

    summary = (await client.get("/api/dashboard/summary")).json()
    assert summary["approved_count"] == 1


async def test_approved_count_ignores_rejected(client):
    async with SessionLocal() as session:
        job = Job(description="Job bi reject")
        session.add(job)
        await session.flush()
        session.add(Application(job_id=job.id, status="rejected"))
        await session.commit()

    summary = (await client.get("/api/dashboard/summary")).json()
    assert summary["approved_count"] == 0


async def test_avg_score_is_null_when_no_match_results(client):
    summary = (await client.get("/api/dashboard/summary")).json()
    assert summary["avg_score"] is None


async def test_avg_score_counts_latest_match_result_per_job_only(client):
    """job A có 2 match_result (giả lập phân tích lại) -> chỉ bản mới nhất (90) được tính,
    không phải trung bình (50+90). job B chỉ có 1 match_result (70).
    Kỳ vọng avg = (90 + 70) / 2 = 80, KHÔNG PHẢI (50 + 90 + 70) / 3.
    """
    async with SessionLocal() as session:
        session.add(Resume(id=1, content="CV mau"))
        job_a = Job(description="Job A")
        job_b = Job(description="Job B")
        session.add_all([job_a, job_b])
        await session.flush()

        session.add(
            MatchResult(
                job_id=job_a.id,
                resume_id=1,
                score=50,
                verdict="weak_match",
                reasoning="lan phan tich dau",
                matched_requirements=[],
                missing_requirements=[],
                suggestions=[],
            )
        )
        await session.flush()
        session.add(
            MatchResult(
                job_id=job_a.id,
                resume_id=1,
                score=90,
                verdict="strong_match",
                reasoning="lan phan tich lai, moi hon",
                matched_requirements=[],
                missing_requirements=[],
                suggestions=[],
            )
        )
        session.add(
            MatchResult(
                job_id=job_b.id,
                resume_id=1,
                score=70,
                verdict="good_match",
                reasoning="job B",
                matched_requirements=[],
                missing_requirements=[],
                suggestions=[],
            )
        )
        await session.commit()

    summary = (await client.get("/api/dashboard/summary")).json()
    assert summary["avg_score"] == 80.0
