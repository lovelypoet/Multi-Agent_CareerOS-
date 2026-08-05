"""Test `OllamaClient` — mock `ollama.AsyncClient.chat()`, KHÔNG gọi Ollama thật. Phải chạy
được cả khi máy không cài Ollama (ví dụ trên CI sau này).
"""

from __future__ import annotations

import ollama
import pytest

from app.integrations.ollama_client import DEFAULT_NUM_CTX, OllamaCallError, OllamaClient

# Không có test nào ở đây đụng DB, nhưng vẫn phải khớp loop_scope="session" với các file test
# khác trong suite — mọi file dùng chung 1 SessionLocal/engine module-level (conftest.py, scope
# session). Để mặc định loop function-scoped sẽ làm hỏng event loop mà engine đó đang gắn vào,
# khiến các test file chạy SAU (thứ tự alphabet) crash với "Future attached to a different loop"
# dù code chúng hoàn toàn đúng — đã tự tay verify bug này khi thêm file test mới.
pytestmark = pytest.mark.asyncio(loop_scope="session")


def _fake_chat_response(
    content: str,
    *,
    model: str = "qwen2.5:7b",
    prompt_eval_count: int | None = 44,
    eval_count: int | None = 7,
    done_reason: str | None = "stop",
) -> ollama.ChatResponse:
    return ollama.ChatResponse(
        model=model,
        message=ollama.Message(role="assistant", content=content),
        prompt_eval_count=prompt_eval_count,
        eval_count=eval_count,
        done_reason=done_reason,
    )


class _FakeAsyncClient:
    """Thay `ollama.AsyncClient` thật — trả về response/lỗi đã định sẵn, ghi lại lời gọi."""

    def __init__(self, calls: list[dict[str, object]], response=None, error: Exception | None = None):
        self._calls = calls
        self._response = response
        self._error = error

    async def chat(self, *, model, messages, options=None, **kwargs):
        self._calls.append({"model": model, "messages": messages, "options": options})
        if self._error is not None:
            raise self._error
        return self._response


@pytest.fixture
def fake_ollama(monkeypatch):
    """Thay `ollama.AsyncClient` bằng bản giả. Trả về list các lời gọi để assert."""

    calls: list[dict[str, object]] = []

    def _install(response=None, error: Exception | None = None):
        monkeypatch.setattr(
            ollama,
            "AsyncClient",
            lambda host=None: _FakeAsyncClient(calls, response=response, error=error),
        )
        return calls

    return _install


class TestOllamaClientParsing:
    async def test_parses_text_and_usage_from_response(self, fake_ollama):
        calls = fake_ollama(
            response=_fake_chat_response('{"score": 70}', prompt_eval_count=120, eval_count=30)
        )
        client = OllamaClient()

        result = await client.complete(system="sys", user_content="user")

        assert result.text == '{"score": 70}'
        assert result.model == "qwen2.5:7b"
        assert result.input_tokens == 120
        assert result.output_tokens == 30
        assert result.stop_reason == "stop"
        assert result.latency_ms >= 0
        assert len(calls) == 1

    async def test_builds_system_as_first_message(self, fake_ollama):
        calls = fake_ollama(response=_fake_chat_response("ok"))
        client = OllamaClient()

        await client.complete(system="Ban la chuyen gia tuyen dung", user_content="Phan tich JD nay")

        messages = calls[0]["messages"]
        assert messages[0] == {"role": "system", "content": "Ban la chuyen gia tuyen dung"}
        assert messages[1] == {"role": "user", "content": "Phan tich JD nay"}

    async def test_sets_num_ctx_explicitly(self, fake_ollama):
        """Ollama mặc định context window nhỏ (2048-4096) dù model hỗ trợ tới 128K — không set
        tường minh thì resume+JD dài có thể bị cắt ngầm, lỗi âm thầm không báo gì cả."""
        calls = fake_ollama(response=_fake_chat_response("ok"))
        client = OllamaClient()

        await client.complete(system="sys", user_content="user")

        assert calls[0]["options"]["num_ctx"] == DEFAULT_NUM_CTX

    async def test_missing_usage_fields_become_none_not_error(self, fake_ollama):
        """prompt_eval_count/eval_count có thể vắng mặt với prompt dài -- hạn chế đã biết của
        Ollama (không phải bug ở code mình) -- lưu None, không throw lỗi."""
        fake_ollama(response=_fake_chat_response("ok", prompt_eval_count=None, eval_count=None))
        client = OllamaClient()

        result = await client.complete(system="sys", user_content="user")

        assert result.input_tokens is None
        assert result.output_tokens is None

    async def test_empty_message_content_becomes_empty_string_not_none(self, fake_ollama):
        fake_ollama(response=_fake_chat_response(None))
        client = OllamaClient()

        result = await client.complete(system="sys", user_content="user")

        assert result.text == ""


class TestOllamaClientErrors:
    async def test_response_error_wrapped_with_pull_hint(self, fake_ollama):
        fake_ollama(error=ollama.ResponseError("model 'qwen2.5:7b' not found", status_code=404))
        client = OllamaClient()

        with pytest.raises(OllamaCallError) as exc_info:
            await client.complete(system="sys", user_content="user")

        assert "ollama pull" in str(exc_info.value)

    async def test_connection_error_wrapped_with_serve_hint_not_raw_traceback(self, fake_ollama):
        fake_ollama(error=ConnectionRefusedError("[Errno 111] Connection refused"))
        client = OllamaClient()

        with pytest.raises(OllamaCallError) as exc_info:
            await client.complete(system="sys", user_content="user")

        assert "ollama serve" in str(exc_info.value)
