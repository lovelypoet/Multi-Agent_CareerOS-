"""Nơi DUY NHẤT trong codebase gọi Ollama (local model). Cùng triết lý với
`integrations/anthropic.py` — implement chung interface `LLMClient`
(`integrations/llm_client.py`), `matching_agent.py` chọn client nào qua
`settings.llm_provider`, không cần biết chi tiết provider.

Dùng API gốc của Ollama qua `ollama.AsyncClient().chat(...)` (không dùng endpoint tương
thích OpenAI) — đơn giản hơn, và async để không chặn event loop của FastAPI.

Ép JSON bằng `format=<json schema>` (structured output thật của Ollama — model chỉ được
sinh token khớp schema) thay vì chỉ nhắc trong system prompt rồi hy vọng, lỡ sai thì mới
bắt bằng fallback parser. `format` là tham số CHUNG của `ollama.chat()`, không riêng cho
1 agent nào — hiện tại chỉ có `matching_agent` nên hardcode thẳng `MatchOutput` ở đây cho
đơn giản; nếu sau này có thêm agent khác dùng `OllamaClient`, cần thêm tham số
`response_schema` vào `LLMClient.complete()` để truyền schema linh hoạt hơn, không nên
over-engineer cho 1 agent duy nhất.
"""

from __future__ import annotations

import time

import ollama

from app.core.config import get_settings
from app.integrations.llm_client import LLMResponse
from app.schemas.match import MatchOutput

# Ollama mặc định context window khá nhỏ (2048-4096 tuỳ version) dù qwen2.5:7b hỗ trợ tới
# 128K — không set tường minh, resume+JD dài có thể bị cắt NGẦM, model phân tích thiếu dữ
# liệu mà không báo lỗi gì (lỗi âm thầm, dễ bỏ sót vì không crash, chỉ ra kết quả tệ hơn).
DEFAULT_NUM_CTX = 8192


class OllamaCallError(RuntimeError):
    """Gọi Ollama thất bại — chưa chạy `ollama serve`, model chưa pull, lỗi mạng, timeout..."""


class OllamaClient:
    def __init__(self, *, model: str | None = None) -> None:
        settings = get_settings()
        self._settings = settings
        # Cho phép chỉ định model tường minh (ví dụ ensemble mode cần 2 instance, 2 model khác
        # nhau, cùng lúc) — mặc định vẫn dùng settings.ollama_model nếu không truyền.
        self._model = model or settings.ollama_model
        self._client = ollama.AsyncClient(host=settings.ollama_host)

    @property
    def model(self) -> str:
        return self._model

    async def complete(
        self,
        *,
        system: str,
        user_content: str,
        max_tokens: int | None = None,
        temperature: float = 0.0,
        num_ctx: int = DEFAULT_NUM_CTX,
    ) -> LLMResponse:
        """Gọi model 1 lần, trả về text thô + usage — cùng shape với `AnthropicClient.complete`.

        Ollama không nhận `system` riêng như Anthropic — phải build thành message đầu tiên
        trong mảng `messages`.
        """
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]

        options: dict[str, object] = {"temperature": temperature, "num_ctx": num_ctx}
        if max_tokens is not None:
            options["num_predict"] = max_tokens

        started = time.perf_counter()
        try:
            response = await self._client.chat(
                model=self._model,
                messages=messages,
                options=options,
                format=MatchOutput.model_json_schema(),
            )
        except ollama.ResponseError as exc:
            raise OllamaCallError(
                f"Ollama trả lỗi: {exc}. Kiểm tra đã chạy `ollama pull {self._model}` chưa."
            ) from exc
        except Exception as exc:  # kết nối bị từ chối, timeout, ollama serve chưa chạy...
            raise OllamaCallError(
                f"Không gọi được Ollama tại {self._settings.ollama_host}: {exc}. "
                "Kiểm tra `ollama serve` đang chạy chưa."
            ) from exc

        # Tự đo latency giống hệt anthropic.py — không dùng total_duration của Ollama vì
        # đơn vị/ý nghĩa có thể khác, đo nhất quán theo 1 cách cho mọi provider.
        latency_ms = int((time.perf_counter() - started) * 1000)

        # prompt_eval_count/eval_count có thể sai hoặc vắng mặt với prompt dài, đặc biệt khi
        # vượt num_ctx — hạn chế đã biết của Ollama (xem GitHub issue), không phải bug ở đây.
        # Nếu vắng mặt thì lưu None, không throw lỗi.
        return LLMResponse(
            text=response.message.content or "",
            model=response.model or self._model,
            input_tokens=response.prompt_eval_count,
            output_tokens=response.eval_count,
            latency_ms=latency_ms,
            stop_reason=response.done_reason,
        )
