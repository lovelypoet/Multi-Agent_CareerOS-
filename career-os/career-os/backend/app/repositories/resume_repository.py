"""Persistence operations for immutable resume versions."""

from __future__ import annotations

import hashlib

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.resume import Resume

_RESUME_LOCK_NAMESPACE = 1_128_513_106
_RESUME_LOCK_KEY = 1
_RETRYABLE_EXTRACTION_STATES = ("pending", "failed", "unverified")
_RETRYABLE_EMBEDDING_STATES = ("pending", "failed", "unverified")


class ResumeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_active(self) -> Resume | None:
        return await self.session.scalar(select(Resume).where(Resume.is_active.is_(True)))

    async def get_by_id(self, resume_id: int) -> Resume | None:
        return await self.session.get(Resume, resume_id)

    async def create_or_get_active_version(self, *, content: str) -> tuple[Resume, bool]:
        """Create an immutable version, or reuse the active row for identical content.

        A transaction-level advisory lock serializes even the first insert, when no row exists
        that could otherwise be locked. The partial unique index remains the database backstop.
        """
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(:namespace, :lock_key)"),
            {"namespace": _RESUME_LOCK_NAMESPACE, "lock_key": _RESUME_LOCK_KEY},
        )
        active = await self.get_active()
        if (
            active is not None
            and active.content_hash == content_hash
            and active.content == content
        ):
            return active, False

        if active is not None:
            active.is_active = False
            await self.session.flush()

        latest_version = await self.session.scalar(select(func.max(Resume.version_number)))
        resume = Resume(
            content=content,
            content_hash=content_hash,
            version_number=(latest_version or 0) + 1,
            is_active=True,
        )
        self.session.add(resume)
        await self.session.flush()
        return resume, True

    async def claim_extraction(self, *, resume_id: int) -> bool:
        result = await self.session.execute(
            update(Resume)
            .where(
                Resume.id == resume_id,
                Resume.extraction_status.in_(_RETRYABLE_EXTRACTION_STATES),
            )
            .values(
                extraction_status="running",
                extraction_error=None,
                embedding_status="blocked",
                embedding_error=None,
            )
        )
        return result.rowcount == 1

    async def complete_extraction(self, *, resume_id: int, status: str) -> None:
        await self.session.execute(
            update(Resume)
            .where(Resume.id == resume_id)
            .values(
                extraction_status=status,
                extraction_error=None,
                embedding=None,
                embedding_status="pending" if status == "succeeded" else "empty",
                embedding_error=None,
            )
        )

    async def fail_extraction(self, *, resume_id: int, error: str) -> None:
        await self.session.execute(
            update(Resume)
            .where(Resume.id == resume_id)
            .values(
                extraction_status="failed",
                extraction_error=error,
                embedding_status="blocked",
                embedding_error=None,
            )
        )

    async def claim_embedding(self, *, resume_id: int) -> bool:
        result = await self.session.execute(
            update(Resume)
            .where(
                Resume.id == resume_id,
                Resume.extraction_status == "succeeded",
                Resume.embedding_status.in_(_RETRYABLE_EMBEDDING_STATES),
            )
            .values(embedding_status="running", embedding_error=None)
        )
        return result.rowcount == 1

    async def set_embedding(self, *, resume_id: int, embedding: list[float]) -> None:
        await self.session.execute(
            update(Resume)
            .where(Resume.id == resume_id)
            .values(embedding=embedding, embedding_status="succeeded", embedding_error=None)
        )

    async def fail_embedding(self, *, resume_id: int, error: str) -> None:
        await self.session.execute(
            update(Resume)
            .where(Resume.id == resume_id)
            .values(embedding=None, embedding_status="failed", embedding_error=error)
        )
