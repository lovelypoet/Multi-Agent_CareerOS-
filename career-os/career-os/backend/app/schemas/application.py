"""Schema request/response cho trạng thái approve/reject."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

# 4 giá trị hợp lệ trong DB (khớp CHECK constraint) — dùng để đọc dữ liệu ra.
ApplicationStatus = Literal["pending", "approved", "rejected", "applied"]

# Phase 2 chỉ được GHI 2 giá trị này — 'pending' (không có row nghĩa là pending) và
# 'applied' (dành cho Phase 3+) không có đường nào được phép ghi ở đây.
ApplicationUpdatableStatus = Literal["approved", "rejected"]


class ApplicationUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ApplicationUpdatableStatus


class ApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: int
    status: ApplicationStatus
    updated_at: datetime
