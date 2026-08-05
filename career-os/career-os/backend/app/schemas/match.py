"""Schema cho output của matching agent và cho response trả về FE.

`MatchOutput` là bản dịch 1-1 của khối JSON quy định trong `prompts/matching_v1.md`.
Đặt ở `schemas/` (public) vì đây là contract dữ liệu, không phải logic prompt —
cả agent (private) lẫn API (public) đều dựa vào đúng một định nghĩa này.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Verdict = Literal["strong_match", "good_match", "partial_match", "weak_match"]


class MatchOutput(BaseModel):
    """Đúng 6 field, không thừa không thiếu."""

    model_config = ConfigDict(extra="forbid")

    score: int = Field(ge=0, le=100)
    verdict: Verdict
    reasoning: str
    matched_requirements: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)

    @field_validator("matched_requirements", "missing_requirements", "suggestions", mode="before")
    @classmethod
    def _drop_empty_items(cls, value: object) -> object:
        """Model thỉnh thoảng trả phần tử rỗng/None trong mảng — bỏ đi, không để lọt vào DB."""
        if isinstance(value, list):
            return [str(item).strip() for item in value if item is not None and str(item).strip()]
        return value

    @field_validator("reasoning")
    @classmethod
    def _reasoning_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reasoning không được rỗng")
        return value.strip()


class MatchResultRead(MatchOutput):
    """MatchOutput + metadata của row trong DB."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: int
    job_id: int
    resume_id: int
    created_at: datetime
