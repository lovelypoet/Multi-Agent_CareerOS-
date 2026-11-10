"""Job matching use case: coordinate persistence, AI analysis, and scam assessment."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_contract import AgentContext, AgentExecutionError, AgentUnavailableError
from app.core.agent_registry import get_agent
from app.integrations.anthropic import AnthropicConfigError
from app.models.job import Job
from app.models.match_result import MatchResult
from app.repositories.agent_run_repository import AgentRunRepository
from app.repositories.job_repository import JobRepository
from app.repositories.match_result_repository import MatchResultRepository
from app.repositories.resume_repository import ResumeRepository
from app.repositories.scam_assessment_repository import ScamAssessmentRepository
from app.schemas.match import MatchOutput
from app.schemas.scam_detection import ScamDetectionOutput

logger = logging.getLogger(__name__)

MATCHING_AGENT = "matching_agent"
SCAM_DETECTION_AGENT = "scam_detection_agent"


class MatchingServiceError(RuntimeError):
    def __init__(self, message: str, *, job_id: int | None = None) -> None:
        super().__init__(message)
        self.job_id = job_id


class ResumeRequiredError(MatchingServiceError):
    pass


class MatchingAgentUnavailableError(MatchingServiceError):
    pass


class MatchingAgentMisconfiguredError(MatchingServiceError):
    pass


class MatchingExecutionError(MatchingServiceError):
    pass


@dataclass(slots=True)
class MatchingOutcome:
    job: Job
    match: MatchResult | None


class MatchingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def match_job(self, description: str) -> MatchingOutcome:
        resume = await ResumeRepository(self.session).get_active()
        if resume is None:
            raise ResumeRequiredError("A resume must be saved before matching a job.")

        job = await JobRepository(self.session).create(description=description)
        await self.session.commit()
        await self.session.refresh(job)

        await self._run_scam_detection(job)

        try:
            agent = get_agent(MATCHING_AGENT)
        except AgentUnavailableError as exc:
            logger.error("Matching agent unavailable: %s", exc)
            raise MatchingAgentUnavailableError(
                "The matching service is unavailable.", job_id=job.id
            ) from exc
        except AnthropicConfigError as exc:
            logger.error("Matching agent provider is misconfigured: %s", exc)
            raise MatchingAgentMisconfiguredError(
                "The matching provider is not configured.", job_id=job.id
            ) from exc

        run_repo = AgentRunRepository(self.session)
        try:
            result = await agent.run(
                AgentContext(
                    resume_text=resume.content,
                    job_description_text=job.description,
                    job_id=job.id,
                )
            )
        except AgentExecutionError as exc:
            for log in exc.run_logs:
                await run_repo.log(run_log=log, job_id=job.id)
            await self.session.commit()
            logger.warning("Matching agent failed for job %s: %s", job.id, exc)
            raise MatchingExecutionError(
                "The job was saved, but matching failed.", job_id=job.id
            ) from exc

        for log in result.run_logs:
            await run_repo.log(run_log=log, job_id=job.id)

        if result.needs_review:
            await self.session.commit()
            logger.info("Matching models disagreed for job %s; manual review is required.", job.id)
            return MatchingOutcome(job=job, match=None)

        output = MatchOutput.model_validate(result.output)
        match = await MatchResultRepository(self.session).create(
            job_id=job.id, resume_id=resume.id, output=output
        )
        await self.session.commit()
        await self.session.refresh(match)
        return MatchingOutcome(job=job, match=match)

    async def _run_scam_detection(self, job: Job) -> None:
        run_repo = AgentRunRepository(self.session)
        try:
            agent = get_agent(SCAM_DETECTION_AGENT)
        except (AgentUnavailableError, AnthropicConfigError) as exc:
            logger.error("Scam detection agent unavailable for job %s: %s", job.id, exc)
            return

        try:
            result = await agent.run(
                AgentContext(resume_text="", job_description_text=job.description, job_id=job.id)
            )
        except AgentExecutionError as exc:
            for log in exc.run_logs:
                await run_repo.log(run_log=log, job_id=job.id)
            await self.session.commit()
            logger.warning("Scam detection failed for job %s: %s", job.id, exc)
            return

        for log in result.run_logs:
            await run_repo.log(run_log=log, job_id=job.id)

        if result.needs_review:
            await self.session.commit()
            logger.info("Scam detection models disagreed for job %s; manual review is required.", job.id)
            return

        await ScamAssessmentRepository(self.session).upsert(
            job_id=job.id,
            output=ScamDetectionOutput.model_validate(result.output),
        )
        await self.session.commit()
