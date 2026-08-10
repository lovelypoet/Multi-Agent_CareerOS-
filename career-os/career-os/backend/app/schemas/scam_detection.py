"""Schema cho output của scam detection agent và cho response trả về FE.

`ScamDetectionOutput` là bản dịch 1-1 của khối JSON quy định trong `prompts/scam_detection_v1.md`
— bài toán phân loại có cấu trúc, giống `MatchOutput`, KHÔNG phải văn xuôi tự do như
`CoverLetterOutput`. Không có `resume_text`/CV liên quan — agent này chỉ đánh giá bản thân JD.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

RiskLevel = Literal["low", "medium", "high"]


class ScamDetectionOutput(BaseModel):
    """4 field, không thừa không thiếu.

    `is_suspicious`/`risk_level` phải nhất quán — ràng buộc theo đúng rubric trong
    `scam_detection_v1.md`: `is_suspicious = true` khi `risk_level` là `medium`/`high`,
    `is_suspicious = false` chỉ khi `risk_level = low`. Validate lại ở đây thay vì chỉ dặn
    trong prompt — model vẫn có thể trả mâu thuẫn dù đã được dặn, không tin tưởng mù quáng.
    """

    model_config = ConfigDict(extra="forbid")

    is_suspicious: bool
    risk_level: RiskLevel
    red_flags: list[str] = Field(default_factory=list)
    reasoning: str

    @field_validator("red_flags", mode="before")
    @classmethod
    def _drop_empty_items(cls, value: object) -> object:
        if isinstance(value, list):
            return [str(item).strip() for item in value if item is not None and str(item).strip()]
        return value

    @field_validator("reasoning")
    @classmethod
    def _reasoning_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reasoning không được rỗng")
        return value.strip()

    @model_validator(mode="after")
    def _is_suspicious_consistent_with_risk_level(self) -> "ScamDetectionOutput":
        """`model_validator(mode="after")` chứ không phải `field_validator` trên riêng
        `is_suspicious` — thứ tự field trong class không đảm bảo `risk_level` đã có giá trị lúc
        `field_validator` của `is_suspicious` chạy (Pydantic validate theo thứ tự khai báo field,
        `is_suspicious` khai trước `risk_level`). Chạy sau khi TOÀN BỘ field đã có giá trị mới
        chắc chắn đúng.
        """
        expected = self.risk_level != "low"
        if self.is_suspicious != expected:
            raise ValueError(
                f"is_suspicious={self.is_suspicious} mâu thuẫn với risk_level={self.risk_level!r} "
                f"(kỳ vọng is_suspicious={expected})"
            )
        return self


class ScamAssessmentRead(BaseModel):
    """`ScamDetectionOutput` + metadata của row trong DB."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    is_suspicious: bool
    risk_level: RiskLevel
    red_flags: list[str]
    reasoning: str
    created_at: datetime
