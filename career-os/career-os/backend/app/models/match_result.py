"""Bảng `match_results` — các cột khớp CHÍNH XÁC 6 field JSON của prompts/matching_v1.md."""

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, created_at_column

VERDICTS = ("strong_match", "good_match", "partial_match", "weak_match")


class MatchResult(Base):
    __tablename__ = "match_results"
    __table_args__ = (
        CheckConstraint("score >= 0 AND score <= 100", name="ck_match_results_score_range"),
        CheckConstraint(
            "verdict IN ('strong_match', 'good_match', 'partial_match', 'weak_match')",
            name="ck_match_results_verdict",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resume_id: Mapped[int] = mapped_column(
        ForeignKey("resumes.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    score: Mapped[int] = mapped_column(Integer, nullable=False)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    matched_requirements: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    missing_requirements: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    suggestions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = created_at_column()

    job = relationship("Job", back_populates="match_results", lazy="noload")
