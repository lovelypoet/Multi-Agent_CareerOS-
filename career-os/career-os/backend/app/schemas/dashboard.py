"""Schema response cho `GET /api/dashboard/summary`."""

from __future__ import annotations

from pydantic import BaseModel


class DashboardSummary(BaseModel):
    jobs_today: int
    approved_count: int
    # None khi chưa có match_result nào — Postgres AVG() trên tập rỗng trả NULL tự nhiên.
    avg_score: float | None
