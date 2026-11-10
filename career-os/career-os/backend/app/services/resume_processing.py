"""Extract and embed data for one specific resume version."""

from __future__ import annotations

import logging

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_contract import (
    AgentContext,
    AgentExecutionError,
    AgentRunLog,
    AgentUnavailableError,
)
from app.core.agent_registry import get_agent
from app.integrations.anthropic import AnthropicConfigError
from app.integrations.embedding_client import EmbeddingCallError, embed_text
from app.repositories.agent_run_repository import AgentRunRepository
from app.repositories.cv_extraction_repository import CVExtractionRepository
from app.repositories.resume_repository import ResumeRepository
from app.schemas.cv_extraction import CVExtractionOutput

logger = logging.getLogger(__name__)
CV_EXTRACTION_AGENT = "cv_extraction_agent"


async def _log_agent_runs(
    session: AsyncSession, *, run_logs: list[AgentRunLog], resume_id: int
) -> None:
    repository = AgentRunRepository(session)
    for run_log in run_logs:
        await repository.log(run_log=run_log, job_id=None, resume_id=resume_id)


async def process_resume_version(*, resume_id: int, session: AsyncSession) -> None:
    """Process/retry derivations without ever writing them to another resume version."""
    resume_repository = ResumeRepository(session)
    resume = await resume_repository.get_by_id(resume_id)
    if resume is None:
        raise RuntimeError(f"Resume version {resume_id} does not exist.")

    if await resume_repository.claim_extraction(resume_id=resume_id):
        await session.commit()
        await session.refresh(resume)

        try:
            agent = get_agent(CV_EXTRACTION_AGENT)
            result = await agent.run(
                AgentContext(resume_text=resume.content, job_description_text="")
            )
        except (AgentUnavailableError, AnthropicConfigError) as exc:
            logger.error("CV extraction agent unavailable for resume %s: %s", resume_id, exc)
            await resume_repository.fail_extraction(
                resume_id=resume_id, error="CV extraction service is unavailable."
            )
            await session.commit()
            return
        except AgentExecutionError as exc:
            await _log_agent_runs(session, run_logs=exc.run_logs, resume_id=resume_id)
            await resume_repository.fail_extraction(
                resume_id=resume_id, error="CV extraction failed. You can save the same CV to retry."
            )
            await session.commit()
            logger.warning("CV extraction failed for resume %s: %s", resume_id, exc)
            return

        await _log_agent_runs(session, run_logs=result.run_logs, resume_id=resume_id)
        try:
            output = CVExtractionOutput.model_validate(result.output)
        except ValidationError as exc:
            await resume_repository.fail_extraction(
                resume_id=resume_id, error="CV extraction returned invalid data."
            )
            await session.commit()
            logger.warning("CV extraction returned invalid data for resume %s: %s", resume_id, exc)
            return

        extraction_status = (
            "succeeded" if output.domains or output.key_skills else "empty"
        )
        await CVExtractionRepository(session).replace_for_resume(
            resume_id=resume_id, output=output
        )
        await resume_repository.complete_extraction(
            resume_id=resume_id, status=extraction_status
        )
        await session.commit()
        await session.refresh(resume)

    else:
        await session.refresh(resume)

    if resume.extraction_status != "succeeded":
        return
    if resume.embedding_status in {"succeeded", "running"}:
        return

    extracted = await CVExtractionRepository(session).get_for_resume(resume_id)
    if extracted is None:
        raise RuntimeError(
            f"Resume {resume_id} is marked extracted but has no version-scoped keyword record."
        )
    combined_text = ", ".join([*extracted.domains, *extracted.key_skills])
    if not combined_text:
        raise RuntimeError(
            f"Resume {resume_id} has succeeded extraction status but no extracted keywords."
        )
    if not await resume_repository.claim_embedding(resume_id=resume_id):
        await session.commit()
        return
    await session.commit()

    try:
        embedding = await embed_text(combined_text)
    except EmbeddingCallError as exc:
        await resume_repository.fail_embedding(
            resume_id=resume_id, error="Resume embedding generation failed."
        )
        await session.commit()
        logger.warning("Could not embed resume %s: %s", resume_id, exc)
        return

    await resume_repository.set_embedding(resume_id=resume_id, embedding=embedding)
    await session.commit()
