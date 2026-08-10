"""Bảng `cover_letters` — append-only, giống `match_results`.

KHÔNG unique theo `job_id` (khác `resumes` là upsert-singleton) — cover letter đặc thù theo từng
job, và người dùng có thể muốn tạo lại (đổi giọng văn, thử lại nếu chưa ưng), nên cho phép nhiều
row/job. FE luôn hiện bản mới nhất (xem `CoverLetterRepository.get_latest_for_job`).
"""

from datetime import datetime

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_column


class CoverLetter(Base):
    __tablename__ = "cover_letters"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resume_id: Mapped[int] = mapped_column(
        ForeignKey("resumes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = created_at_column()
