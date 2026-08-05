"""Script chạy TAY 1 LẦN — phân tích lại các job đã lưu nhưng chưa từng có `match_result`
(ví dụ vì `ANTHROPIC_API_KEY` là placeholder lúc job được lưu, nay đã sửa đúng key thật).

KHÔNG phải endpoint API, KHÔNG phải worker chạy theo lịch (khác `workers/fetch_jobs.py`) —
chỉ chạy khi cần, không tự động lặp lại:

    cd backend && python -m app.scripts.retry_missing_analyses

Nhắm vào TOÀN BỘ job thiếu match_result, không lọc theo ngày/source — key placeholder có thể
đã sai từ lúc setup ban đầu, không chỉ hôm nay. An toàn tuyệt đối: chỉ xử lý job CHƯA có kết
quả, không đụng job đã có (dù thành công hay đã approve/reject).

Tái sử dụng đúng luồng của `POST /api/jobs/analyze` (api/jobs.py) — cùng repository, cùng
AgentContext, cùng cách log agent_runs. Lấy agent qua `core.agent_registry.get_agent(...)`,
KHÔNG import trực tiếp `app.agents.matching_agent` (giữ đúng ranh giới public/private).
"""

from __future__ import annotations

import asyncio
import logging
import sys

from app.core.agent_contract import AgentContext, AgentExecutionError, AgentUnavailableError
from app.core.agent_registry import get_agent
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.integrations.anthropic import AnthropicConfigError
from app.repositories.agent_run_repository import AgentRunRepository
from app.repositories.job_repository import JobRepository
from app.repositories.match_result_repository import MatchResultRepository
from app.repositories.resume_repository import ResumeRepository
from app.schemas.match import MatchOutput

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)-8s %(name)s: %(message)s")

MATCHING_AGENT = "matching_agent"
# Nghỉ nhỏ giữa các lần gọi — không bắt buộc kỹ thuật, chỉ tránh dồn dập ngay sau khi vừa
# đổi key, đề phòng rate limit tạm thời (khác lý do lịch sự khi scrape ITviec ở Phase 1).
DELAY_BETWEEN_CALLS_SECONDS = 0.7


async def run() -> None:
    settings = get_settings()

    async with SessionLocal() as session:
        resume = await ResumeRepository(session).get_singleton(settings.resume_singleton_id)
        if resume is None:
            print("Chưa có resume nào được lưu — không thể phân tích job nào. Dừng lại.")
            return

        jobs = await JobRepository(session).list_without_match_result()
        print(f"Tìm thấy {len(jobs)} job cần phân tích lại.")
        if not jobs:
            return

        try:
            agent = get_agent(MATCHING_AGENT)
        except AgentUnavailableError as exc:
            print(f"Agent không khả dụng, dừng lại: {exc}")
            return
        except AnthropicConfigError as exc:
            print(f"Cấu hình Anthropic sai, dừng lại: {exc}")
            return

        match_repo = MatchResultRepository(session)
        run_repo = AgentRunRepository(session)

        succeeded = 0
        failed: list[tuple[int, str]] = []

        for index, job in enumerate(jobs, start=1):
            label = job.title or (job.description[:60] + "…")
            print(f"[{index}/{len(jobs)}] Job #{job.id}: {label}")

            try:
                result = await agent.run(
                    AgentContext(
                        resume_text=resume.content,
                        job_description_text=job.description,
                        job_id=job.id,
                    )
                )
            except AgentExecutionError as exc:
                # 1 job lỗi KHÔNG được cản job tiếp theo — chỉ log agent_runs, tiếp tục batch.
                for log in exc.run_logs:
                    await run_repo.log(run_log=log, job_id=job.id)
                await session.commit()
                print(f"  -> LỖI: {exc}")
                failed.append((job.id, str(exc)))
            else:
                await match_repo.create(
                    job_id=job.id,
                    resume_id=resume.id,
                    output=MatchOutput.model_validate(result.output),
                )
                for log in result.run_logs:
                    await run_repo.log(run_log=log, job_id=job.id)
                await session.commit()
                print(f"  -> OK, score={result.output['score']}")
                succeeded += 1

            if index < len(jobs):
                await asyncio.sleep(DELAY_BETWEEN_CALLS_SECONDS)

        print()
        print("=== Tổng kết ===")
        print(f"Tổng số job xử lý: {len(jobs)}")
        print(f"Thành công: {succeeded}")
        print(f"Vẫn lỗi: {len(failed)}")
        for job_id, error in failed:
            print(f"  - Job #{job_id}: {error}")


def main() -> None:
    # print() dùng encoding mặc định của console — trên Windows thường là codepage cp1252,
    # không decode được tiếng Việt và crash ngay ở dòng in đầu tiên (đã tự tay verify bug
    # này, cùng loại với lỗi alembic.ini ở Phase 0). Ép UTF-8 cho toàn bộ output của script.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(run())


if __name__ == "__main__":
    main()
