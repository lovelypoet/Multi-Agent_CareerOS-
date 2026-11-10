"""Read and replace extracted keywords scoped to one immutable resume version."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cv_extracted_keywords import CVExtractedKeywords
from app.schemas.cv_extraction import CVExtractionOutput


class CVExtractionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_for_resume(self, resume_id: int) -> CVExtractedKeywords | None:
        return await self.session.get(CVExtractedKeywords, resume_id)

    async def replace_for_resume(
        self, *, resume_id: int, output: CVExtractionOutput
    ) -> CVExtractedKeywords:
        values = {"domains": output.domains, "key_skills": output.key_skills}
        stmt = (
            pg_insert(CVExtractedKeywords)
            .values(resume_id=resume_id, **values)
            .on_conflict_do_update(
                index_elements=[CVExtractedKeywords.resume_id],
                set_={**values, "updated_at": func.now()},
            )
            .returning(CVExtractedKeywords)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()
