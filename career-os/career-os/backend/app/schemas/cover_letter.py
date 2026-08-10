"""Schema cho output của cover letter agent và cho response trả về FE.

`CoverLetterOutput` là bản dịch 1-1 của khối JSON quy định trong `prompts/cover_letter_v1.md` —
đơn giản hơn `MatchOutput` nhiều vì cover letter là văn xuôi liền mạch, không nên ép cấu trúc
rời rạc kiểu kết quả phân tích matching.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class CoverLetterOutput(BaseModel):
    """Đúng 1 field, không thừa không thiếu."""

    model_config = ConfigDict(extra="forbid")

    cover_letter_text: str

    @field_validator("cover_letter_text")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("cover_letter_text không được rỗng")
        return value.strip()


class CoverLetterRead(BaseModel):
    """`CoverLetterOutput` + metadata của row trong DB."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    resume_id: int
    content: str
    created_at: datetime
