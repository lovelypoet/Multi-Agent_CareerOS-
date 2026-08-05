"""Declarative base + kiểu cột dùng chung cho toàn bộ model."""

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def created_at_column() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )


def updated_at_column() -> Mapped[datetime]:
    """`onupdate=` chỉ kích hoạt qua UPDATE thông thường của ORM — KHÔNG tự chạy khi upsert
    bằng `ON CONFLICT DO UPDATE` (xem `ApplicationRepository.upsert`, phải liệt kê tường minh
    `updated_at: func.now()` trong `set_`). Vẫn khai `onupdate=` ở đây cho đường update thường.
    """
    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
