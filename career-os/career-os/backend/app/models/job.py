"""Bảng `jobs` — mỗi lần dán tay (Phase 0) hoặc fetch tự động (Phase 1) là 1 row mới (giữ lịch sử)."""

from datetime import datetime

from sqlalchemy import CheckConstraint, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, created_at_column

SOURCES = ("manual", "itviec")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("source IN ('manual', 'itviec')", name="ck_jobs_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Phase 0: FE chỉ có 1 textarea nên title/company để NULL cho job dán tay.
    # Phase 1: job fetch từ ITviec điền đủ title/company/url.
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    company: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # UNIQUE (cho phép nhiều NULL — Postgres không coi NULL trùng NULL) — cơ chế dedup
    # chính cho job fetch tự động ở Phase 1. Job dán tay ở Phase 0 vẫn để NULL.
    url: Mapped[str | None] = mapped_column(String(2000), nullable=True, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # 'manual' = dán tay (Phase 0), 'itviec' = tự fetch (Phase 1).
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default="manual")
    created_at: Mapped[datetime] = created_at_column()

    match_results = relationship(
        "MatchResult",
        back_populates="job",
        cascade="all, delete-orphan",
        lazy="noload",
    )
