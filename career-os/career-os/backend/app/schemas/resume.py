"""Schema request/response cho resume."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_RESUME_CHARS = 60_000


class ResumeUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=MAX_RESUME_CHARS)

    @field_validator("content")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("content không được rỗng")
        return cleaned


class ResumeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    content: str
    version_number: int
    is_active: bool
    extraction_status: Literal["pending", "running", "succeeded", "empty", "failed", "unverified"]
    extraction_error: str | None
    embedding_status: Literal[
        "pending", "running", "succeeded", "empty", "failed", "blocked", "unverified"
    ]
    embedding_error: str | None
    created_at: datetime
