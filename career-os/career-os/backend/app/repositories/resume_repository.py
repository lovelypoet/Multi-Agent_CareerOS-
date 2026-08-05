"""Truy vấn bảng `resumes` — Phase 0 chỉ tồn tại đúng 1 row ở id cố định."""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.resume import Resume


class ResumeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_singleton(self, resume_id: int) -> Resume | None:
        return await self.session.get(Resume, resume_id)

    async def upsert_singleton(self, *, resume_id: int, content: str) -> Resume:
        """UPDATE row duy nhất, KHÔNG BAO GIỜ INSERT thêm row mới cho mỗi lần lưu.

        Nếu insert row mới mỗi lần, `resume_id` trong `match_results` sẽ không còn trỏ tới bản
        resume mới nhất. Dùng ON CONFLICT để thao tác này nguyên tử (atomic), không bị race giữa
        2 request lưu resume cùng lúc.

        Lưu ý: ở Phase 0 mọi resume đều nằm ở đúng `resume_id` này nên việc chỉ định id thủ công
        (sequence không tự tăng) là an toàn. Khi nào có multi-resume thì chuyển sang insert
        không truyền id và phải đồng bộ lại sequence trước.
        """
        stmt = (
            pg_insert(Resume)
            .values(id=resume_id, content=content)
            .on_conflict_do_update(index_elements=[Resume.id], set_={"content": content})
            .returning(Resume)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()
