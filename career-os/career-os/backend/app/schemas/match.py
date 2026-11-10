"""Schema cho output của matching agent và cho response trả về FE.

`MatchOutput` là bản dịch 1-1 của khối JSON quy định trong `prompts/matching_v1.md`.
Đặt ở `schemas/` (public) vì đây là contract dữ liệu, không phải logic prompt —
cả agent (private) lẫn API (public) đều dựa vào đúng một định nghĩa này.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AliasPath, BaseModel, ConfigDict, Field, field_validator

Verdict = Literal["strong_match", "good_match", "partial_match", "weak_match"]
RequirementPriority = Literal["required", "preferred"]
RequirementCategory = Literal[
    "skill",
    "experience",
    "education",
    "responsibility",
    "location",
    "other",
]
EvidenceStatus = Literal["met", "partial", "missing"]


class JDRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=500)
    priority: RequirementPriority
    category: RequirementCategory
    jd_quote: str = Field(min_length=1, max_length=1000)

    @field_validator("text", "jd_quote")
    @classmethod
    def _trim_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Requirement text and quote must not be blank.")
        return cleaned


class JDAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_title: str | None = Field(default=None, max_length=300)
    experience_level: str | None = Field(default=None, max_length=200)
    tech_stack: list[str] = Field(default_factory=list, max_length=30)
    requirements: list[JDRequirement] = Field(default_factory=list, max_length=20)

    @field_validator("tech_stack", mode="before")
    @classmethod
    def _clean_tech_stack(cls, value: object) -> object:
        if isinstance(value, list):
            return [str(item).strip() for item in value if item is not None and str(item).strip()]
        return value


class RequirementAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_index: int = Field(ge=0, le=19)
    status: EvidenceStatus
    cv_evidence: str = Field(default="", max_length=1000)

    @field_validator("cv_evidence")
    @classmethod
    def _trim_evidence(cls, value: str) -> str:
        return value.strip()


class MatchOutput(BaseModel):
    """Validated match result plus optional source-grounded JD analysis."""

    model_config = ConfigDict(extra="forbid")

    score: int = Field(ge=0, le=100)
    verdict: Verdict
    reasoning: str
    matched_requirements: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    jd_analysis: JDAnalysis | None = None
    requirement_assessments: list[RequirementAssessment] = Field(default_factory=list, max_length=20)

    @field_validator(
        "matched_requirements", "missing_requirements", "suggestions", mode="before"
    )
    @classmethod
    def _drop_empty_items(cls, value: object) -> object:
        """Model thỉnh thoảng trả phần tử rỗng/None trong mảng — bỏ đi, không để lọt vào DB."""
        if isinstance(value, list):
            return [str(item).strip() for item in value if item is not None and str(item).strip()]
        return value

    @field_validator("requirement_assessments", mode="before")
    @classmethod
    def _none_assessments_are_empty(cls, value: object) -> object:
        return [] if value is None else value

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
    resume_version_number: int = Field(validation_alias=AliasPath("resume", "version_number"))
    analysis_basis: Literal["evidence_based", "legacy"]
    created_at: datetime
