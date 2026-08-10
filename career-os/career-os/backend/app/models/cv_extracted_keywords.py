"""Bảng `cv_extracted_keywords` — singleton, giống `resumes`, quan hệ 1-1 với `resumes`.

Dùng `resume_id` làm PRIMARY KEY luôn (không tạo `id` riêng + hằng số "giá trị cố định" như
`resumes` đã phải làm): `resumes` phải dùng hằng số vì nó là singleton GỐC, không có gì để khóa
theo. Bảng này thì khác — nó vốn dĩ quan hệ 1-1 với `resumes`, nên `resume_id` tự nó đã đủ để đảm
bảo tính singleton, không cần thêm quy ước "luôn insert với ID cố định X" phải nhớ áp dụng đúng
mỗi lần — đơn giản hơn, ít chỗ để làm sai hơn.

Singleton, KHÔNG phải append-only: chỉ giữ kết quả trích xuất MỚI NHẤT, không giữ lịch sử (CV cũ
cũng không được giữ lại) — dùng upsert qua `ON CONFLICT (resume_id) DO UPDATE`.
"""

from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_column, updated_at_column


class CVExtractedKeywords(Base):
    __tablename__ = "cv_extracted_keywords"

    resume_id: Mapped[int] = mapped_column(
        ForeignKey("resumes.id", ondelete="CASCADE"), primary_key=True
    )
    domains: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    key_skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
