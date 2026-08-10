"""Bảng `scam_assessments` — 1 job chỉ có ĐÚNG 1 assessment mới nhất có ý nghĩa.

Khác `match_results`/`cover_letters` (cho phép nhiều row/job, giữ lịch sử) — không có lý do
nghiệp vụ nào cần giữ lịch sử nhiều lần đánh giá scam cho cùng 1 job, nên dùng UNIQUE trên
`job_id` + upsert khi phân tích lại (giống thiết kế `applications` ở Phase 2), đơn giản hơn kỹ
thuật ROW_NUMBER() mà `match_results` cần dùng.
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_column

RISK_LEVELS = ("low", "medium", "high")


class ScamAssessment(Base):
    __tablename__ = "scam_assessments"
    __table_args__ = (
        CheckConstraint(
            "risk_level IN ('low', 'medium', 'high')", name="ck_scam_assessments_risk_level"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # unique=True đã tự tạo index backing cho constraint này, không cần thêm index=True.
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    is_suspicious: Mapped[bool] = mapped_column(nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    red_flags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = created_at_column()
