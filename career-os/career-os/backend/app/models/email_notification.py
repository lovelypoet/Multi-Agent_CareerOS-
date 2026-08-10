"""Bảng `email_notifications` — LƯU MỌI email đã được `email_classifier_agent` xử lý, kể cả
`is_relevant = false`. Bảng này chính là bản ghi dedup đầy đủ theo `(account_email,
gmail_message_id)` — chỉ LỌC theo `is_relevant = true` ở tầng hiển thị (API), không lọc ở tầng
lưu trữ.

BUG ĐÃ TỰ PHÁT HIỆN VÀ TRÁNH TỪ ĐẦU: nếu chỉ lưu khi `is_relevant = true`, dedup sẽ KHÔNG hoạt
động cho email "không liên quan" — email đó gửi qua LLM lại ở mọi lần quét sau (còn trong cửa sổ
lookback), tốn tiền vô ích tích luỹ dần theo thời gian.

KHÔNG lưu toàn văn email — chỉ `summary` do model tạo ra + metadata cần thiết (người gửi, tiêu
đề, thời gian). Gmail vẫn là nguồn dữ liệu gốc đầy đủ.
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_column

CATEGORIES = ("rejection", "interview_invite", "follow_up_question", "other_relevant")


class EmailNotification(Base):
    __tablename__ = "email_notifications"
    __table_args__ = (
        CheckConstraint(
            "category IN ('rejection', 'interview_invite', 'follow_up_question', 'other_relevant')"
            " OR category IS NULL",
            name="ck_email_notifications_category",
        ),
        # Khóa KÉP, không phải unique đơn trên gmail_message_id — ID này chỉ đảm bảo duy nhất
        # trong phạm vi 1 hộp thư, không có xác nhận chính thức nào từ Google rằng 2 tài khoản
        # khác nhau không bao giờ trùng ID. Coi 1 email là duy nhất theo CẶP (tài khoản, message
        # ID), giống tinh thần dedup theo `url` đã làm ở Phase 1 cho `jobs`.
        UniqueConstraint("account_email", "gmail_message_id", name="uq_email_notifications_account_message"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    gmail_message_id: Mapped[str] = mapped_column(String(100), nullable=False)
    is_relevant: Mapped[bool] = mapped_column(nullable=False)
    job_id: Mapped[int | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    company_name_mentioned: Mapped[str | None] = mapped_column(String(500), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    sender: Mapped[str] = mapped_column(String(500), nullable=False)
    subject: Mapped[str] = mapped_column(String(1000), nullable=False)
    # Thời gian email THẬT (từ Gmail) — KHÁC created_at (thời điểm CareerOS xử lý/lưu).
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = created_at_column()
