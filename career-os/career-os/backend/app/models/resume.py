"""Bảng `resumes` — Phase 0 chỉ có đúng 1 row (id cố định), không multi-user."""

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_column

# Dimension thật của `nomic-embed-text-v2-moe`, đã tự verify — xem `integrations/embedding_client.py`.
EMBEDDING_DIM = 768


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Phase 3 việc #4 — tính từ `domains` + `key_skills` (cv_extracted_keywords), KHÔNG phải
    # toàn văn `content`: phía job chỉ dùng từ khóa ngắn (title+tags), giữ 2 phía cùng "hình
    # dạng" văn bản để cosine similarity so sánh công bằng hơn. NULL nếu chưa từng lưu resume,
    # CV extraction lỗi, hoặc trích ra rỗng — xem `api/resume.py::_run_cv_extraction`.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    created_at: Mapped[datetime] = created_at_column()
