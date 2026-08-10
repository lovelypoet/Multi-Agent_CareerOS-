"""Schema cho output của email classifier agent và cho response trả về FE.

`EmailClassificationOutput` là bản dịch 1-1 của khối JSON quy định trong
`prompts/email_classification_v1.md`. KHÔNG có field `job_id` — model không biết ID thật trong
DB, để nó tự "chọn" 1 ID sẽ có nguy cơ bịa số không tồn tại. Model chỉ trích xuất tên công ty
dạng text (`company_name_mentioned`); code (không phải model) tự đối chiếu tên này với
`jobs.company` sau đó để tìm `job_id` phù hợp (xem `workers/fetch_emails.py`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.schemas.job import JobRead

EmailCategory = Literal["rejection", "interview_invite", "follow_up_question", "other_relevant"]


class EmailClassificationOutput(BaseModel):
    """4 field, không thừa không thiếu."""

    model_config = ConfigDict(extra="forbid")

    is_relevant: bool
    category: EmailCategory | None
    company_name_mentioned: str | None
    summary: str

    @field_validator("summary")
    @classmethod
    def _summary_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("summary không được rỗng")
        return value.strip()

    @field_validator("company_name_mentioned")
    @classmethod
    def _blank_company_becomes_none(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            return None
        return value.strip() if value else value

    @model_validator(mode="after")
    def _category_consistent_with_is_relevant(self) -> "EmailClassificationOutput":
        """`category` PHẢI là `None` khi `is_relevant=False` (bộ lọc cổ điển chỉ là gợi ý thô,
        model mới là bước xác nhận thật — email không liên quan thì không có category), và
        PHẢI có giá trị khi `is_relevant=True` (email liên quan phải thuộc đúng 1 trong 4 loại,
        không để mơ hồ)."""
        if not self.is_relevant and self.category is not None:
            raise ValueError("category phải là null khi is_relevant=False")
        if self.is_relevant and self.category is None:
            raise ValueError("category không được null khi is_relevant=True")
        return self


class EmailNotificationRead(BaseModel):
    """`EmailClassificationOutput` + metadata của row trong DB."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    account_email: str
    gmail_message_id: str
    is_relevant: bool
    job_id: int | None
    category: EmailCategory | None
    company_name_mentioned: str | None
    summary: str
    sender: str
    subject: str
    received_at: datetime
    created_at: datetime


class EmailNotificationWithJob(BaseModel):
    """1 item trả về cho FE — kèm `JobRead` nếu `job_id` khớp được với đúng 1 job (xem mục 4)."""

    model_config = ConfigDict(from_attributes=True)

    notification: EmailNotificationRead
    job: JobRead | None = None
