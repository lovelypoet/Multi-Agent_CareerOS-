"""Truy vấn bảng `agent_runs` — log mọi lần chạy agent, thành công lẫn thất bại."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_contract import AgentRunLog
from app.models.agent_run import AgentRun

# Cắt bớt error rất dài (traceback / HTML trang lỗi của provider) trước khi lưu.
MAX_ERROR_CHARS = 4000


class AgentRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def log(self, *, run_log: AgentRunLog, job_id: int | None) -> AgentRun:
        error = run_log.error
        if error and len(error) > MAX_ERROR_CHARS:
            error = error[:MAX_ERROR_CHARS] + "... (truncated)"

        run = AgentRun(
            agent_name=run_log.agent_name,
            job_id=job_id,
            prompt_version=run_log.prompt_version,
            model=run_log.model,
            input_tokens=run_log.input_tokens,
            output_tokens=run_log.output_tokens,
            latency_ms=run_log.latency_ms,
            output=run_log.output,
            error=error,
        )
        self.session.add(run)
        await self.session.flush()
        return run

    async def list_for_job(self, job_id: int, *, agent_name: str | None = None) -> list[AgentRun]:
        """agent_runs của 1 job, theo đúng thứ tự đã ghi (id ASC) — dùng `id` chứ không phải
        `created_at` để sắp xếp: 2 row cùng 1 lần chạy ensemble commit trong cùng 1 transaction
        có thể trùng `created_at` (Postgres `now()` ổn định theo transaction), `id` mới phản ánh
        đúng thứ tự thật.

        `agent_name` tuỳ chọn — lọc chỉ lấy row của đúng agent đó (cần thiết từ khi có >1 agent
        cùng ghi vào bảng này, xem `api/jobs.py::get_job_agent_runs`). Không truyền thì trả TOÀN
        BỘ agent_runs của job, không phân biệt agent nào (hành vi gốc, tương thích ngược).
        """
        stmt = select(AgentRun).where(AgentRun.job_id == job_id)
        if agent_name is not None:
            stmt = stmt.where(AgentRun.agent_name == agent_name)
        stmt = stmt.order_by(AgentRun.id.asc())
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows)
