"""Nơi DUY NHẤT trong codebase gọi Ollama để tạo embedding — file RIÊNG, KHÔNG gộp vào
`ollama_client.py`: embedding là năng lực khác hẳn chat/completion, `LLMClient.complete()`
xoay quanh sinh text, không phù hợp cho việc trả về vector, giữ đúng "1 file, 1 trách nhiệm".

Dùng `ollama.embed()` (API hiện tại, `/api/embed`) — KHÔNG dùng `embeddings()`/`/api/embeddings`
số ít đã deprecated. Đã tự tay verify (không chỉ tin theo tài liệu):
  - `response.embeddings` là `list[list[float]]` — `response.embeddings[0]` đúng là 1 vector
    `float` khi `input` là 1 chuỗi đơn, không phải 1 `float` lẻ do index nhầm tầng.
  - Dimension thật của `nomic-embed-text-v2-moe` là 768 (không phải đoán từ tài liệu — Matryoshka
    Representation Learning có thể cho dimension khác tuỳ cấu hình, nên KHÔNG hardcode con số nào
    khác 768 ở bất kỳ đâu dùng model này, kể cả migration).
  - Context window thật (`ollama show nomic-embed-text-v2-moe`) là 512 token — KHÁC với
    `nomic-embed-text` bản gốc (8192, xem `ollama_client.py`). Set tường minh qua `options`,
    không tin giá trị mặc định của Ollama, nhưng cũng không copy nhầm số 8192 của bản gốc sang
    đây — 2 model khác nhau, context window khác nhau.
"""

from __future__ import annotations

import math

import ollama

from app.core.config import get_settings

# Xem docstring module — 512, KHÔNG phải 8192 (đó là của `nomic-embed-text` bản gốc, model khác).
DEFAULT_NUM_CTX = 512

# Dimension thật của `nomic-embed-text-v2-moe`, đã tự verify qua `ollama.embed()` — dùng chung
# hằng số này cho cột `VECTOR(N)` trong models/migration, không lặp lại số 768 rải rác nhiều nơi.
EMBEDDING_DIM = 768


class EmbeddingCallError(RuntimeError):
    """Gọi Ollama để tạo embedding thất bại — chưa chạy `ollama serve`, chưa pull model, lỗi
    mạng, timeout... Cùng triết lý với `OllamaCallError` ở `ollama_client.py`."""


async def embed_text(text: str) -> list[float]:
    """Tạo embedding cho 1 chuỗi văn bản, dùng `settings.embedding_model` qua Ollama local."""
    settings = get_settings()
    client = ollama.AsyncClient(host=settings.ollama_host)

    try:
        response = await client.embed(
            model=settings.embedding_model,
            input=text,
            options={"num_ctx": DEFAULT_NUM_CTX},
        )
    except ollama.ResponseError as exc:
        raise EmbeddingCallError(
            f"Ollama trả lỗi khi tạo embedding: {exc}. "
            f"Kiểm tra đã chạy `ollama pull {settings.embedding_model}` chưa."
        ) from exc
    except Exception as exc:  # kết nối bị từ chối, timeout, ollama serve chưa chạy...
        raise EmbeddingCallError(
            f"Không gọi được Ollama tại {settings.ollama_host}: {exc}. "
            "Kiểm tra `ollama serve` đang chạy chưa."
        ) from exc

    return list(response.embeddings[0])


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Python thuần — KHÔNG dùng numpy chỉ để làm 1 phép tính đơn giản này (dự án chưa có
    numpy, không đáng thêm dependency mới cho việc nhỏ này)."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b)
