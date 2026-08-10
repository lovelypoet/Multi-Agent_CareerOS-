"""Schema cho output của CV extraction agent và cho response trả về FE.

`CVExtractionOutput` là bản dịch 1-1 của khối JSON quy định trong `prompts/cv_extraction_v1.md`.
Giới hạn SỐ LƯỢNG phần tử (`max_length`), không chỉ độ chung chung của từng từ — nếu không giới
hạn số lượng, model vẫn có thể trả về 30-40 mục cho 1 CV ngắn, gây nhiễu theo cách khác (danh sách
quá dài làm loãng tín hiệu khi hợp vào bộ lọc Phase 1, xem `workers/fetch_jobs.py`). Pydantic tự
chặn ở tầng validate nếu model cố nhét nhiều hơn, không cần code thêm.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CVExtractionOutput(BaseModel):
    """Đúng 2 field, không thừa không thiếu."""

    model_config = ConfigDict(extra="forbid")

    domains: list[str] = Field(default_factory=list, max_length=5)
    key_skills: list[str] = Field(default_factory=list, max_length=15)

    @field_validator("domains", "key_skills", mode="before")
    @classmethod
    def _drop_empty_items(cls, value: object) -> object:
        """Model thỉnh thoảng trả phần tử rỗng/None trong mảng — bỏ đi, không để lọt vào DB.
        Tái dùng đúng pattern đã có ở `MatchOutput` (`schemas/match.py`), không viết lại logic mới.
        """
        if isinstance(value, list):
            return [str(item).strip() for item in value if item is not None and str(item).strip()]
        return value


class CVExtractedKeywordsRead(BaseModel):
    """`CVExtractionOutput` + metadata của row trong DB."""

    model_config = ConfigDict(from_attributes=True)

    resume_id: int
    domains: list[str]
    key_skills: list[str]
    updated_at: datetime
    created_at: datetime
