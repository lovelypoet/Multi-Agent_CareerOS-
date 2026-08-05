"""Schema request/response cho job."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.application import ApplicationStatus
from app.schemas.match import MatchResultRead

# Giới hạn mềm để tránh gửi nhầm cả trang HTML vào API và đốt token vô ích.
MAX_DESCRIPTION_CHARS = 60_000

JobSource = Literal["manual", "itviec"]

# Suy ra từ dữ liệu (jobs + match_results + agent_runs), KHÔNG lưu thành cột riêng — xem
# `JobRepository.list_with_latest_match_and_status` để biết thứ tự ưu tiên xác định giá trị này.
AnalysisStatus = Literal["analyzed", "failed", "needs_review", "pending"]


class JobAnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1, max_length=MAX_DESCRIPTION_CHARS)

    @field_validator("description")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("description không được rỗng")
        return cleaned


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str | None
    company: str | None
    url: str | None
    description: str
    source: JobSource
    created_at: datetime


class JobWithMatch(BaseModel):
    """1 item trong danh sách lịch sử: job + match_result mới nhất + trạng thái approve/reject.

    `application_status` đã được COALESCE về 'pending' ngay trong query (xem
    `JobRepository.list_with_latest_match_and_status`) — job chưa từng approve/reject vẫn
    luôn có giá trị ở đây, không phải None.
    """

    model_config = ConfigDict(from_attributes=True)

    job: JobRead
    match: MatchResultRead | None = None
    application_status: ApplicationStatus
    analysis_status: AnalysisStatus


class JobAnalyzeResponse(BaseModel):
    job: JobRead
    # None khi ensemble bất đồng (needs_review) — job vẫn được lưu, agent_runs vẫn đủ 2 row,
    # chỉ là không có match_result đáng tin để trả về ngay.
    match: MatchResultRead | None = None
