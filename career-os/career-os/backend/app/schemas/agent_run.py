"""Schema response cho `GET /api/jobs/{job_id}/agent-runs` — xem lại thô từng lần gọi agent.

Không giới hạn dùng riêng cho trạng thái 'needs_review' — endpoint chung cho mọi job, hữu ích
để debug lịch sử chạy agent bất kỳ lúc nào.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AgentRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    model: str | None
    prompt_version: str
    output: dict | None
    error: str | None
    created_at: datetime
