"""Versioned resume records for the current single-user application."""

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_column

EMBEDDING_DIM = 768


class Resume(Base):
    __tablename__ = "resumes"
    __table_args__ = (
        UniqueConstraint("version_number", name="uq_resumes_version_number"),
        CheckConstraint("version_number > 0", name="ck_resumes_version_number_positive"),
        CheckConstraint(
            "extraction_status IN "
            "('pending', 'running', 'succeeded', 'empty', 'failed', 'unverified')",
            name="ck_resumes_extraction_status",
        ),
        CheckConstraint(
            "embedding_status IN "
            "('pending', 'running', 'succeeded', 'empty', 'failed', 'blocked', 'unverified')",
            name="ck_resumes_embedding_status",
        ),
        Index(
            "uq_resumes_one_active",
            "is_active",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    version_number: Mapped[int] = mapped_column(nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    extraction_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    extraction_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    embedding_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Embedding is derived data for this exact resume version; consumers must also check status.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    created_at: Mapped[datetime] = created_at_column()
