"""Bảng `jobs` — mỗi lần dán tay (Phase 0) hoặc fetch tự động (Phase 1) là 1 row mới (giữ lịch sử)."""

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, created_at_column

SOURCES = ("manual", "itviec")

# Dimension thật của `nomic-embed-text-v2-moe`, đã tự verify — xem `integrations/embedding_client.py`.
EMBEDDING_DIM = 768


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
    # Phase 3 việc #4 — tính từ title + skill tags (dữ liệu RẺ, cùng tầng với bộ lọc từ khóa),
    # KHÔNG phải từ full description. NULL cho job cũ trước tính năng này, không backfill bắt
    # buộc. Dùng để tìm kiếm theo ý nghĩa (`GET /api/jobs/search`, `.cosine_distance()`).
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    created_at: Mapped[datetime] = created_at_column()

    match_results = relationship(
        "MatchResult",
        back_populates="job",
        cascade="all, delete-orphan",
        lazy="noload",
    )
