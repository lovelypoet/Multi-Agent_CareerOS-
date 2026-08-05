"""Bảng `applications` — trạng thái approve/reject của user cho từng job.

Thiết kế LAZY: KHÔNG có row cho job chưa từng được approve/reject. Row chỉ được tạo khi
user bấm Approve/Reject lần đầu (upsert theo `job_id`, xem `ApplicationRepository`). Khi
đọc, dùng `COALESCE(status, 'pending')` — không có row nghĩa là 'pending', không phải
có row với status='pending'.
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_column, updated_at_column

# 'pending' và 'applied' nằm trong constraint để tương thích Phase 3+ (auto-apply sẽ ghi
# 'applied'), nhưng code Phase 2 chỉ được ghi 'approved'/'rejected' — xem ApplicationUpdateRequest.
STATUSES = ("pending", "approved", "rejected", "applied")


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'applied')",
            name="ck_applications_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # unique=True đã tự tạo index backing cho constraint này, không cần thêm index=True.
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
