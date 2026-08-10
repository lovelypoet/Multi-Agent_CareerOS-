"""Test `integrations/embedding_client.py` — fake `ollama.AsyncClient.embed()`, KHÔNG gọi
Ollama thật trong test tự động (cùng convention với `test_ollama_client.py`). `cosine_similarity()`
là hàm Python thuần, test độc lập không cần DB/Ollama.
"""

from __future__ import annotations

import math

import ollama
import pytest

from app.integrations.embedding_client import DEFAULT_NUM_CTX, EMBEDDING_DIM, EmbeddingCallError, cosine_similarity, embed_text

# Chỉ áp dụng cho từng hàm async cụ thể bên dưới — `TestCosineSimilarity` và
# `test_embedding_dim_is_768_not_guessed_from_docs` là test thuần, đồng bộ, không cần asyncio.
async_test = pytest.mark.asyncio(loop_scope="session")


# --- cosine_similarity — Python thuần, vector biết trước đáp án --------------------------


class TestCosineSimilarity:
    def test_identical_vectors_give_similarity_one(self):
        vector = [0.5, -1.2, 3.0, 0.0]
        assert cosine_similarity(vector, vector) == pytest.approx(1.0)

    def test_orthogonal_vectors_give_similarity_zero(self):
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors_give_similarity_negative_one(self):
        assert cosine_similarity([1.0, 2.0], [-1.0, -2.0]) == pytest.approx(-1.0)

    def test_known_angle(self):
        # (1,0) vs (1,1) -> cos(45 deg) = sqrt(2)/2
        assert cosine_similarity([1.0, 0.0], [1.0, 1.0]) == pytest.approx(math.sqrt(2) / 2)


# --- embed_text — fake ollama.AsyncClient.embed(), không gọi mạng thật -------------------


class _FakeAsyncClient:
    """Thay `ollama.AsyncClient` thật — trả về response/lỗi đã định sẵn, ghi lại lời gọi."""

    def __init__(self, calls: list[dict[str, object]], embeddings=None, error: Exception | None = None):
        self._calls = calls
        self._embeddings = embeddings
        self._error = error

    async def embed(self, *, model, input, options=None, **kwargs):  # noqa: A002
        self._calls.append({"model": model, "input": input, "options": options})
        if self._error is not None:
            raise self._error
        return ollama.EmbedResponse(model=model, embeddings=self._embeddings)


@pytest.fixture
def fake_ollama_embed(monkeypatch):
    """Thay `ollama.AsyncClient` bằng bản giả. Trả về list các lời gọi để assert."""

    calls: list[dict[str, object]] = []

    def _install(embeddings=None, error: Exception | None = None):
        monkeypatch.setattr(
            ollama,
            "AsyncClient",
            lambda host=None: _FakeAsyncClient(calls, embeddings=embeddings, error=error),
        )
        return calls

    return _install


@async_test
async def test_embed_text_returns_first_embedding_as_plain_list(fake_ollama_embed):
    fake_vector = [0.1, 0.2, 0.3]
    calls = fake_ollama_embed(embeddings=[fake_vector])

    result = await embed_text("cau tieng viet bat ky")

    assert result == fake_vector
    assert isinstance(result, list)
    assert calls[0]["input"] == "cau tieng viet bat ky"


@async_test
async def test_embed_text_sets_num_ctx_explicitly(fake_ollama_embed):
    """Nhắc lại bug đã gặp với `nomic-embed-text` (context mặc định của Ollama nhỏ hơn thật) —
    áp dụng lại ở đây, set tường minh qua `options`. Số 512 (KHÔNG phải 8192 của bản gốc) — đã
    tự verify qua `ollama show nomic-embed-text-v2-moe`, xem docstring module."""
    calls = fake_ollama_embed(embeddings=[[0.0]])

    await embed_text("noi dung")

    assert calls[0]["options"] == {"num_ctx": DEFAULT_NUM_CTX}
    assert DEFAULT_NUM_CTX == 512


@async_test
async def test_embed_text_uses_configured_embedding_model(fake_ollama_embed):
    calls = fake_ollama_embed(embeddings=[[0.0]])

    await embed_text("noi dung")

    assert calls[0]["model"] == "nomic-embed-text-v2-moe"


@async_test
async def test_connection_error_wrapped_with_serve_hint_not_raw_traceback(fake_ollama_embed):
    fake_ollama_embed(error=ConnectionRefusedError("[Errno 111] Connection refused"))

    with pytest.raises(EmbeddingCallError) as exc_info:
        await embed_text("noi dung")

    assert "ollama serve" in str(exc_info.value)


@async_test
async def test_response_error_wrapped_with_pull_hint(fake_ollama_embed):
    fake_ollama_embed(error=ollama.ResponseError("model not found", status_code=404))

    with pytest.raises(EmbeddingCallError) as exc_info:
        await embed_text("noi dung")

    assert "ollama pull" in str(exc_info.value)
    assert "nomic-embed-text-v2-moe" in str(exc_info.value)


def test_embedding_dim_is_768_not_guessed_from_docs():
    """Dimension thật đã tự verify qua chạy `ollama.embed()` thật, in ra
    `len(response.embeddings[0])` — KHÔNG đoán từ tài liệu (model dùng Matryoshka Representation
    Learning, dimension có thể khác tuỳ cấu hình, xem docstring module)."""
    assert EMBEDDING_DIM == 768
