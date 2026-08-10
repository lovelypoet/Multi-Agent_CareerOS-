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

from app.core.agent_contract import AgentUnavailableError  # noqa: E402
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
        # `Base.metadata.create_all` KHÔNG tự chạy migration — cột kiểu `VECTOR` (Phase 3 việc
        # #4) cần extension `vector` tồn tại trước, giống lý do phải làm đúng thứ tự này trong
        # migration 0009. Idempotent, an toàn chạy lại giữa các lần test.
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session", autouse=True)
async def _clean_tables():
    """Mỗi test bắt đầu với DB trống, kể cả sequence (để id dự đoán được)."""
    async with SessionLocal() as session:
        await session.execute(
            text(
                "TRUNCATE agent_runs, match_results, cover_letters, scam_assessments, "
                "email_notifications, applications, jobs, resumes RESTART IDENTITY CASCADE"
            )
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


def _default_scam_agent():
    """Fake `scam_detection_agent` mặc định — an toàn, không nghi ngờ.

    `scam_detection_agent` giờ chạy ĐỘC LẬP trong CÙNG luồng `analyze_job`/`run_fetch_jobs` như
    `matching_agent` (xem Phase 3 việc #3 mục 5) — mọi test hiện có gọi 2 endpoint/worker này,
    kể cả test không quan tâm gì tới scam, đều cần 1 fake hợp lệ cho agent này để không lỡ gọi
    Anthropic thật (key giả `test-key-not-used` sẽ khiến `AnthropicClient` thật cố gắng gọi
    mạng và treo/lỗi 401, làm test chậm và phụ thuộc mạng).
    """
    from app.agents.scam_detection_agent import ScamDetectionAgent

    fake_client = FakeAnthropicClient(
        responses=[
            '{"is_suspicious": false, "risk_level": "low", "red_flags": [], '
            '"reasoning": "Khong tim thay dau hieu dang ngo trong JD."}'
        ]
    )
    return ScamDetectionAgent(client=fake_client)


@pytest.fixture
def _agent_registry_patch(monkeypatch):
    """Registry giả DÙNG CHUNG cho `fake_agent`/`fake_scam_agent` — dispatch theo tên, KHÔNG trả
    nhầm agent cho tên khác.

    BUG ĐÃ VERIFY VÀ SỬA: bản cũ patch `get_agent` bằng 1 lambda trả về LUÔN CÙNG 1 agent bất kể
    tên nào được truyền vào (`lambda name: agent`). An toàn khi chỉ có `matching_agent` gọi qua
    `get_agent` trong `api/jobs.py`/`workers/fetch_jobs.py`, nhưng từ khi `scam_detection_agent`
    cũng chạy độc lập trong CÙNG 2 nơi đó, lambda cũ vô tình trả nhầm agent matching cho lời gọi
    `get_agent("scam_detection_agent")` — agent scam chạy nhầm bằng client/response của matching,
    parse ra sai schema, gây lỗi test không liên quan gì tới bug thật đang test.
    """
    registry: dict[str, object] = {}

    def _dispatch(name: str):
        try:
            return registry[name]
        except KeyError as exc:
            raise AgentUnavailableError(
                f"Chưa cài agent giả nào tên '{name}' trong test (registry: {list(registry)})."
            ) from exc

    monkeypatch.setattr("app.api.jobs.get_agent", _dispatch)
    monkeypatch.setattr("app.workers.fetch_jobs.get_agent", _dispatch)
    monkeypatch.setattr("app.scripts.retry_missing_analyses.get_agent", _dispatch)
    monkeypatch.setattr("app.workers.fetch_emails.get_agent", _dispatch)
    return registry


@pytest.fixture
def fake_agent(_agent_registry_patch):
    """Thay `matching_agent` thật bằng agent dùng `FakeAnthropicClient`.

    Tự động cài thêm 1 `scam_detection_agent` giả AN TOÀN mặc định (`setdefault` — không ghi đè
    nếu test đã dùng `fake_scam_agent` để cài agent scam cụ thể trước đó, bất kể thứ tự gọi 2
    fixture này trong test) — xem `_default_scam_agent()`.
    """

    def _install(responses: list[str] | None = None, raise_error: Exception | None = None):
        from app.agents.matching_agent import MatchingAgent

        fake_client = FakeAnthropicClient(responses=responses, raise_error=raise_error)
        agent = MatchingAgent(client=fake_client)
        _agent_registry_patch["matching_agent"] = agent
        _agent_registry_patch.setdefault("scam_detection_agent", _default_scam_agent())
        return fake_client

    return _install


@pytest.fixture
def fake_scam_agent(_agent_registry_patch):
    """Cài (hoặc ghi đè) `scam_detection_agent` giả cụ thể — dùng khi test cần kiểm tra hành vi
    riêng của agent này (is_suspicious/risk_level/ensemble/lỗi...), khác với fake mặc định "an
    toàn, không nghi ngờ" mà `fake_agent` tự cài."""

    def _install(
        responses: list[str] | None = None,
        raise_error: Exception | None = None,
        ensemble_clients: list | None = None,
    ):
        from app.agents.scam_detection_agent import ScamDetectionAgent

        if ensemble_clients is not None:
            agent = ScamDetectionAgent(ensemble_clients=ensemble_clients)
            _agent_registry_patch["scam_detection_agent"] = agent
            return None

        fake_client = FakeAnthropicClient(responses=responses, raise_error=raise_error)
        agent = ScamDetectionAgent(client=fake_client)
        _agent_registry_patch["scam_detection_agent"] = agent
        return fake_client

    return _install


@pytest.fixture
def fake_email_classifier_agent(_agent_registry_patch):
    """Cài `email_classifier_agent` giả — dùng registry dùng chung, đúng nguyên tắc dispatch
    theo tên (xem `_agent_registry_patch`). `run_fetch_emails` là entry point RIÊNG, không bao
    giờ gọi `matching_agent`/`scam_detection_agent`, nên KHÔNG cần tự cài fake mặc định cho 2
    agent đó như `fake_agent`/`fake_scam_agent` đã làm cho `analyze_job`/`run_fetch_jobs`."""

    def _install(
        responses: list[str] | None = None,
        raise_error: Exception | None = None,
        ensemble_clients: list | None = None,
    ):
        from app.agents.email_classifier_agent import EmailClassifierAgent

        if ensemble_clients is not None:
            agent = EmailClassifierAgent(ensemble_clients=ensemble_clients)
            _agent_registry_patch["email_classifier_agent"] = agent
            return None

        fake_client = FakeAnthropicClient(responses=responses, raise_error=raise_error)
        agent = EmailClassifierAgent(client=fake_client)
        _agent_registry_patch["email_classifier_agent"] = agent
        return fake_client

    return _install


@pytest.fixture(autouse=True)
def _cv_extraction_agent_slot(monkeypatch):
    """`cv_extraction_agent` giờ chạy TỰ ĐỘNG, ĐỒNG BỘ ngay trong `POST /api/resume` VÀ
    `POST /api/resume/upload` (xem Phase 3 việc #4 mục 5) — khác các agent trước (chỉ chạy khi
    có fixture cụ thể request nó), 2 endpoint resume này được dùng làm SETUP thông thường ở khắp
    test suite (rất nhiều file gọi `_save_resume(client)`/`client.post("/api/resume", ...)` chỉ
    để có resume, không liên quan gì tới cv_extraction_agent). Vì phạm vi ảnh hưởng quá rộng để
    bắt từng test tự khai báo 1 fixture riêng, patch này BẮT BUỘC autouse — nếu không, mọi test
    gọi 2 endpoint đó sẽ lỡ gọi Anthropic thật (key giả `test-key-not-used` → 401 thật, chậm và
    phụ thuộc mạng — đã tự tay verify bug này ngay khi thêm agent thứ 5).

    Fake mặc định trả `"{}"` (không cấu hình response cụ thể) — hợp lệ vì `domains`/`key_skills`
    đều có default rỗng, nên parse ra `CVExtractionOutput(domains=[], key_skills=[])` mỗi lần,
    an toàn cho việc gọi lặp lại nhiều lần trong 1 test (vd lưu resume 4 lần) mà không cần cấp
    sẵn danh sách response dài.

    Dùng 1 "slot" (dict 1 phần tử) thay vì gán thẳng agent vào lambda — để `fake_cv_extraction_agent`
    (bên dưới) có thể GHI ĐÈ đúng agent đang dùng bất kể thứ tự 2 fixture được yêu cầu trong 1
    test, vì lambda luôn đọc giá trị HIỆN TẠI trong dict tại thời điểm gọi, không chụp giá trị
    lúc patch.
    """
    from app.agents.cv_extraction_agent import CVExtractionAgent

    slot = {"agent": CVExtractionAgent(client=FakeAnthropicClient())}
    monkeypatch.setattr("app.api.resume.get_agent", lambda name: slot["agent"])
    return slot


@pytest.fixture
def fake_cv_extraction_agent(_cv_extraction_agent_slot):
    """Ghi đè fake mặc định — dùng khi test cần kiểm tra hành vi cụ thể của cv_extraction_agent
    (response tuỳ ý, lỗi giả lập...)."""

    def _install(responses: list[str] | None = None, raise_error: Exception | None = None):
        from app.agents.cv_extraction_agent import CVExtractionAgent

        fake_client = FakeAnthropicClient(responses=responses, raise_error=raise_error)
        _cv_extraction_agent_slot["agent"] = CVExtractionAgent(client=fake_client)
        return fake_client

    return _install


@pytest.fixture(autouse=True)
def _embedding_slot(monkeypatch):
    """`embed_text` (Phase 3 việc #4) giờ được gọi TỰ ĐỘNG từ `api/resume.py` (sau CV extraction,
    nếu domains/key_skills không rỗng) và `workers/fetch_jobs.py` (khi `resumes.embedding` khác
    NULL) — patch BẮT BUỘC autouse, cùng lý do với `_cv_extraction_agent_slot`: rất nhiều test
    không liên quan gì tới embedding vẫn đi qua 2 chỗ này, không được lỡ gọi Ollama thật.

    Fake mặc định trả vector "one-hot" suy từ `hash(text)` — 2 chuỗi input KHÁC NHAU luôn cho
    vector TRỰC GIAO (cosine similarity = 0), không vô tình làm lọt qua điều kiện embedding ở
    `fetch_jobs.py` cho các test không chủ đích test tính năng này (vd job/resume ngẫu nhiên
    trong test khác vô tình có similarity cao do fake trả cùng 1 vector cố định).

    Track TOÀN BỘ lời gọi vào `slot["calls"]` bất kể fake mặc định hay `fake_embedding_client`
    (bên dưới) đang cài — để test có thể assert "KHÔNG gọi embed_text" mà không cần cài gì thêm.
    """
    from app.integrations.embedding_client import EMBEDDING_DIM

    def _default_fn(text: str) -> list[float]:
        vector = [0.0] * EMBEDDING_DIM
        vector[hash(text) % EMBEDDING_DIM] = 1.0
        return vector

    slot: dict[str, object] = {"fn": _default_fn, "calls": []}

    async def _dispatch(text: str) -> list[float]:
        slot["calls"].append(text)
        return slot["fn"](text)

    monkeypatch.setattr("app.api.resume.embed_text", _dispatch)
    monkeypatch.setattr("app.api.jobs.embed_text", _dispatch)
    monkeypatch.setattr("app.workers.fetch_jobs.embed_text", _dispatch)
    return slot


@pytest.fixture
def fake_embedding_client(_embedding_slot):
    """Ghi đè fake mặc định — cho phép test chỉ định vector CỤ THỂ cho từng chuỗi input (để ép
    similarity vượt/không vượt ngưỡng có chủ đích), hoặc mô phỏng lỗi kết nối Ollama.

    Trả về `_embedding_slot["calls"]` — danh sách input THẬT đã gửi cho `embed_text()`, theo
    đúng thứ tự gọi — dùng để assert nội dung chuỗi gửi đi, không chỉ assert có gọi hay không.
    """

    def _install(
        vectors: dict[str, list[float]] | None = None,
        raise_error: Exception | None = None,
    ) -> list[str]:
        vectors = vectors or {}

        def _fn(text: str) -> list[float]:
            if raise_error is not None:
                raise raise_error
            if text not in vectors:
                raise AssertionError(
                    f"fake_embedding_client: chưa cấu hình vector cho input: {text!r}"
                )
            return vectors[text]

        _embedding_slot["fn"] = _fn
        return _embedding_slot["calls"]

    return _install


@pytest.fixture
def fake_cover_letter_agent(monkeypatch):
    """Thay `cover_letter_agent` thật bằng agent dùng `FakeAnthropicClient` — agent này luôn
    dùng Anthropic (xem `cover_letter_agent.py`), không cần fake Ollama."""

    def _install(responses: list[str] | None = None, raise_error: Exception | None = None):
        from app.agents.cover_letter_agent import CoverLetterAgent

        fake_client = FakeAnthropicClient(responses=responses, raise_error=raise_error)
        agent = CoverLetterAgent(client=fake_client)
        monkeypatch.setattr("app.api.cover_letters.get_agent", lambda name: agent)
        return fake_client

    return _install
