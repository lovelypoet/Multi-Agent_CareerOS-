"""Fixture cho test Phase 0.

Test chạy trên Postgres thật (DB riêng `careeros_test`) vì code dùng JSONB, ON CONFLICT và
window function — SQLite không mô phỏng đúng những thứ đó, test qua SQLite sẽ cho cảm giác an
toàn giả. Anthropic API thì được thay bằng client giả, không tốn tiền và không phụ thuộc mạng.
"""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://careeros:careeros@127.0.0.1:5432/careeros_test"
)
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-used")

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.db import SessionLocal, engine  # noqa: E402
from app.integrations.anthropic import LLMResponse  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402

pytest_plugins = ("pytest_asyncio",)


class FakeAnthropicClient:
    """Client giả: trả về text đã định sẵn, ghi lại prompt để test kiểm tra."""

    def __init__(self, responses: list[str] | None = None, raise_error: Exception | None = None):
        self.responses = responses or []
        self.raise_error = raise_error
        self.calls: list[dict[str, str]] = []
        self.model = "fake-model"

    async def complete(self, *, system: str, user_content: str, **kwargs) -> LLMResponse:
        self.calls.append({"system": system, "user_content": user_content})
        if self.raise_error is not None:
            raise self.raise_error
        text_out = self.responses.pop(0) if self.responses else "{}"
        return LLMResponse(
            text=text_out,
            model=self.model,
            input_tokens=1234,
            output_tokens=567,
            latency_ms=42,
        )


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def _create_schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session", autouse=True)
async def _clean_tables():
    """Mỗi test bắt đầu với DB trống, kể cả sequence (để id dự đoán được)."""
    async with SessionLocal() as session:
        await session.execute(
            text("TRUNCATE agent_runs, match_results, jobs, resumes RESTART IDENTITY CASCADE")
        )
        await session.commit()
    yield


@pytest_asyncio.fixture(loop_scope="session")
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def valid_match_json() -> str:
    return (
        '{"score": 72, "verdict": "good_match", '
        '"reasoning": "Ứng viên có 3 năm React đúng yêu cầu must-have, thiếu TypeScript rõ ràng.", '
        '"matched_requirements": ["React 3+ năm"], '
        '"missing_requirements": ["TypeScript", "Python (nice-to-have)"], '
        '"suggestions": ["Thêm dự án dùng TypeScript vào CV"]}'
    )


@pytest.fixture
def fake_agent(monkeypatch):
    """Thay agent thật bằng agent dùng FakeAnthropicClient.

    Patch cả 3 nơi gọi `get_agent` (api/jobs.py của Phase 0, workers/fetch_jobs.py của
    Phase 1, scripts/retry_missing_analyses.py) — mỗi module import `get_agent` vào
    namespace riêng nên phải patch từng chỗ.
    """

    def _install(responses: list[str] | None = None, raise_error: Exception | None = None):
        from app.agents.matching_agent import MatchingAgent

        fake_client = FakeAnthropicClient(responses=responses, raise_error=raise_error)
        agent = MatchingAgent(client=fake_client)
        monkeypatch.setattr("app.api.jobs.get_agent", lambda name: agent)
        monkeypatch.setattr("app.workers.fetch_jobs.get_agent", lambda name: agent)
        monkeypatch.setattr("app.scripts.retry_missing_analyses.get_agent", lambda name: agent)
        return fake_client

    return _install
