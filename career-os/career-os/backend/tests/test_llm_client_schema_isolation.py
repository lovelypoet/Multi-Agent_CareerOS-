"""Test TỔNG QUÁT chống tái diễn bug đã gặp: `OllamaClient` (client DÙNG CHUNG cho mọi agent
qua `LLM_PROVIDER=ollama`/`ollama_ensemble`) từng hardcode `format=MatchOutput.model_json_schema()`
ngay trong tầng tích hợp — khiến `cv_extraction_agent`/`scam_detection_agent`/
`email_classifier_agent` thất bại 100% (Ollama ép output đúng hình dạng `MatchOutput` bất kể
agent nào gọi, dù prompt yêu cầu field khác hẳn — đã tự tay verify bằng traceback
`extra_forbidden`/`missing` thật khi chạy qua Ollama thật, xem báo cáo điều tra).

Sửa tận gốc: `response_schema` giờ PHẢI do CHÍNH agent gọi truyền vào `LLMClient.complete()`,
`OllamaClient`/`AnthropicClient` không tự quyết định schema nào. File này verify ở tầng THẤP
NHẤT có thể — bắt chính xác `format=` thật được gửi tới `ollama.AsyncClient.chat()` — cho CẢ 4
agent dùng cấu trúc JSON (`matching`, `scam_detection`, `email_classifier`, `cv_extraction`;
`cover_letter_agent` luôn dùng Anthropic nên không chạm `OllamaClient`, xem test riêng ở dưới).
KHÔNG tiêm client giả — để agent tự dựng `OllamaClient` thật qua `_build_default_client`/
`_build_client`, đúng đường đi thật lúc bug xảy ra, không bỏ qua bước quyết định provider.

RÀ CODE THẬT trước khi viết: mỗi agent (`matching_agent.py`, `scam_detection_agent.py`,
`email_classifier_agent.py`) đọc `settings.llm_provider` qua tên `get_settings` IMPORT VÀO
MODULE CỦA CHÍNH NÓ (`from app.core.config import get_settings`), không phải qua
`app.core.config.get_settings` — patch phải nhắm đúng namespace từng module (đúng pattern đã
có ở `test_cv_extraction_agent.py::test_ollama_ensemble_provider_still_uses_single_model_not_ensemble`),
patch nhầm chỗ sẽ khiến agent vẫn đọc settings thật (mặc định `anthropic`), test âm thầm không
test được gì (false negative).

MỞ RỘNG CHO AGENT THỨ 5/6 dùng JSON schema qua Ollama: thêm 1 entry vào `_AGENT_CASES`, chạy lại
`test_each_agent_sends_its_own_schema_to_ollama` — không cần viết test mới.
"""

from __future__ import annotations

import json

import ollama
import pytest

from app.agents.cv_extraction_agent import CVExtractionAgent
from app.agents.email_classifier_agent import EmailClassifierAgent
from app.agents.matching_agent import MatchingAgent
from app.agents.scam_detection_agent import ScamDetectionAgent
from app.core.agent_contract import AgentContext
from app.core.config import get_settings
from app.integrations.anthropic import AnthropicClient
from app.integrations.ollama_client import OllamaClient
from app.schemas.cv_extraction import CVExtractionOutput
from app.schemas.email_notification import EmailClassificationOutput
from app.schemas.match import MatchOutput
from app.schemas.scam_detection import ScamDetectionOutput

async_test = pytest.mark.asyncio(loop_scope="session")


def _fake_chat_response(content: str) -> ollama.ChatResponse:
    return ollama.ChatResponse(
        model="qwen2.5:7b",
        message=ollama.Message(role="assistant", content=content),
        prompt_eval_count=10,
        eval_count=5,
        done_reason="stop",
    )


class _FakeAsyncClient:
    """Bắt CHÍNH XÁC tham số `format=` thật đã gửi cho `ollama.chat()` — bằng chứng trực tiếp
    nhất có thể lấy được rằng agent nào gửi schema nào, không suy luận gián tiếp qua hành vi
    parse output."""

    def __init__(self, calls: list[dict], response_content: str) -> None:
        self._calls = calls
        self._response_content = response_content

    async def chat(self, *, model, messages, options=None, format=None, **kwargs):  # noqa: A002
        self._calls.append({"model": model, "format": format})
        return _fake_chat_response(self._response_content)


@pytest.fixture
def fake_ollama_chat(monkeypatch):
    """Thay `ollama.AsyncClient` bằng bản giả — trả về `response_content` cố định (nội dung
    parse ra đúng/sai không quan trọng, file này CHỈ quan tâm `format=` thật đã gửi đi)."""
    calls: list[dict] = []

    def _install(response_content: str = "{}") -> list[dict]:
        monkeypatch.setattr(
            ollama, "AsyncClient", lambda host=None: _FakeAsyncClient(calls, response_content)
        )
        return calls

    return _install


def _force_provider(monkeypatch, *, agent_module: str, provider: str) -> None:
    """Patch `get_settings` ĐÚNG namespace module của agent — xem docstring file."""
    settings = get_settings().model_copy(update={"llm_provider": provider})
    monkeypatch.setattr(f"{agent_module}.get_settings", lambda: settings)


# (tên_agent, module_path, factory, response_content_hợp_lệ_tối_thiểu, schema_class, agent_context)
_AGENT_CASES = [
    (
        "matching_agent",
        "app.agents.matching_agent",
        MatchingAgent,
        '{"score": 50, "verdict": "partial_match", "reasoning": "ok"}',
        MatchOutput,
        AgentContext(resume_text="CV", job_description_text="JD"),
    ),
    (
        "scam_detection_agent",
        "app.agents.scam_detection_agent",
        ScamDetectionAgent,
        '{"is_suspicious": false, "risk_level": "low", "reasoning": "ok"}',
        ScamDetectionOutput,
        AgentContext(resume_text="", job_description_text="JD"),
    ),
    (
        "email_classifier_agent",
        "app.agents.email_classifier_agent",
        EmailClassifierAgent,
        '{"is_relevant": false, "category": null, "company_name_mentioned": null, "summary": "ok"}',
        EmailClassificationOutput,
        AgentContext(
            resume_text="",
            job_description_text="",
            metadata={"sender": "a@b.com", "subject": "s", "body_text": "b"},
        ),
    ),
    (
        "cv_extraction_agent",
        "app.agents.cv_extraction_agent",
        CVExtractionAgent,
        '{"domains": [], "key_skills": []}',
        CVExtractionOutput,
        AgentContext(resume_text="CV", job_description_text=""),
    ),
]


@async_test
@pytest.mark.parametrize(
    "name,module_path,agent_cls,response_content,schema_class,context",
    _AGENT_CASES,
    ids=[case[0] for case in _AGENT_CASES],
)
async def test_each_agent_sends_its_own_schema_to_ollama(
    monkeypatch, fake_ollama_chat, name, module_path, agent_cls, response_content, schema_class, context
):
    _force_provider(monkeypatch, agent_module=module_path, provider="ollama")
    calls = fake_ollama_chat(response_content)

    agent = agent_cls()
    await agent.run(context)

    assert len(calls) >= 1
    for call in calls:
        assert call["format"] == schema_class.model_json_schema(), (
            f"{name}: format= gửi cho Ollama KHÔNG khớp schema riêng của agent này — đây chính "
            f"xác là lớp bug đã gặp (agent dùng nhầm/không có schema của agent khác)."
        )


@async_test
async def test_ensemble_mode_sends_same_schema_to_both_clients(monkeypatch, fake_ollama_chat):
    """Ensemble gọi `complete()` 2 lần (model chính + model phụ) — cả 2 PHẢI cùng 1 schema, xem
    docstring module: KHÔNG được mỗi model 1 schema khác nhau."""
    _force_provider(monkeypatch, agent_module="app.agents.scam_detection_agent", provider="ollama_ensemble")
    calls = fake_ollama_chat('{"is_suspicious": false, "risk_level": "low", "reasoning": "ok"}')

    agent = ScamDetectionAgent()
    await agent.run(AgentContext(resume_text="", job_description_text="JD bat ky"))

    assert len(calls) == 2  # model chính + model phụ
    assert calls[0]["format"] == calls[1]["format"] == ScamDetectionOutput.model_json_schema()


@async_test
async def test_cross_agent_schemas_are_all_distinct(monkeypatch, fake_ollama_chat):
    """Assertion QUAN TRỌNG NHẤT — nếu 2 agent BẤT KỲ trong 4 agent này vô tình gửi CÙNG 1
    schema, đó chính là dấu hiệu bug hardcode-chung-1-schema đang tái diễn."""
    captured_schemas: dict[str, dict] = {}

    for name, module_path, agent_cls, response_content, _schema_class, context in _AGENT_CASES:
        _force_provider(monkeypatch, agent_module=module_path, provider="ollama")
        # `fake_ollama_chat` dùng CHUNG 1 list `calls` xuyên suốt vòng lặp (fixture chỉ khởi
        # tạo 1 lần cho cả test) — phải đọc phần tử MỚI NHẤT (`calls[-1]`), không phải
        # `calls[0]` (BUG ĐÃ TỰ VERIFY VÀ SỬA ngay khi viết: đọc nhầm `calls[0]` khiến cả 4
        # agent đều "đọc" ra đúng schema của agent CHẠY ĐẦU TIÊN — lỗi ở tầng test, không phải
        # ở code đang test, nhưng dễ nhầm là bug thật nếu không soát kỹ).
        calls = fake_ollama_chat(response_content)
        agent = agent_cls()
        await agent.run(context)
        captured_schemas[name] = calls[-1]["format"]

    serialized = [json.dumps(schema, sort_keys=True) for schema in captured_schemas.values()]
    assert len(serialized) == len(set(serialized)), (
        f"2 agent trở lên gửi TRÙNG schema cho Ollama — bug hardcode-chung-schema đang tái diễn: "
        f"{list(captured_schemas.keys())}"
    )


@async_test
async def test_ollama_client_omits_format_when_no_schema_given(fake_ollama_chat):
    """`response_schema=None` (không truyền) -> KHÔNG set `format=` gì cả — hành vi trước khi
    có structured output, không phải lỗi."""
    calls = fake_ollama_chat("bat ky text nao, khong ep JSON")
    client = OllamaClient()

    await client.complete(system="sys", user_content="user")

    assert calls[0]["format"] is None


# --- AnthropicClient — nhận response_schema nhưng bỏ qua, không lỗi -----------------------


class _FakeAnthropicMessage:
    def __init__(self, text: str) -> None:
        self.content = [type("Block", (), {"type": "text", "text": text})()]
        self.model = "claude-sonnet-5"
        self.stop_reason = "end_turn"
        self.usage = type("Usage", (), {"input_tokens": 10, "output_tokens": 5})()


class _FakeAnthropicMessages:
    async def create(self, **kwargs):
        return _FakeAnthropicMessage('{"score": 1}')


class _FakeAsyncAnthropic:
    def __init__(self, **kwargs) -> None:
        self.messages = _FakeAnthropicMessages()


@async_test
async def test_anthropic_client_accepts_response_schema_without_error(monkeypatch):
    """`AnthropicClient` không dùng `response_schema` (Claude không có grammar-constrained
    decoding), nhưng PHẢI nhận tham số này mà không lỗi — để khớp interface `LLMClient` chung,
    agent nào cũng gọi `complete(..., response_schema=...)` như nhau bất kể provider."""
    import anthropic as anthropic_module

    monkeypatch.setattr(anthropic_module, "AsyncAnthropic", _FakeAsyncAnthropic)

    client = AnthropicClient()  # đọc ANTHROPIC_API_KEY thật từ env test (conftest.py đã set)
    result = await client.complete(
        system="sys", user_content="user", response_schema=MatchOutput.model_json_schema()
    )

    assert result.text == '{"score": 1}'
