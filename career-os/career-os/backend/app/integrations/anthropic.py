"""Nơi DUY NHẤT trong codebase gọi Anthropic SDK.

Agent không tự khởi tạo client riêng — mọi lời gọi đi qua đây, để sau này đổi model hoặc
đổi provider chỉ phải sửa đúng 1 file. Implement interface `LLMClient` (xem
`integrations/llm_client.py`) — cùng shape với `OllamaClient`, `matching_agent.py` chọn
client nào qua `settings.llm_provider`, không cần biết chi tiết provider.
"""

from __future__ import annotations

import time

import anthropic

from app.core.config import get_settings
from app.integrations.llm_client import LLMResponse


class AnthropicConfigError(RuntimeError):
    """Thiếu API key / cấu hình sai."""


class AnthropicCallError(RuntimeError):
    """Gọi API thất bại (lỗi mạng, rate limit, timeout, provider trả lỗi)."""


class AnthropicClient:
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise AnthropicConfigError(
                "Chưa cấu hình ANTHROPIC_API_KEY. Copy infrastructure/.env.example thành "
                "backend/.env rồi điền key."
            )
        self._settings = settings
        self._client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            timeout=settings.anthropic_timeout_seconds,
        )

    @property
    def model(self) -> str:
        return self._settings.anthropic_model

    async def complete(
        self,
        *,
        system: str,
        user_content: str,
        max_tokens: int | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Gọi model 1 lần, trả về text thô + usage.

        `system` đi qua field `system` của API chứ không nhét vào `messages` — đúng như ghi chú
        triển khai trong prompts/matching_v1.md.
        """
        started = time.perf_counter()
        try:
            message = await self._client.messages.create(
                model=self._settings.anthropic_model,
                max_tokens=max_tokens or self._settings.anthropic_max_tokens,
                temperature=temperature,
                system=system,
                messages=[{"role": "user", "content": user_content}],
            )
        except anthropic.APIError as exc:
            raise AnthropicCallError(f"Anthropic API lỗi: {exc}") from exc
        except Exception as exc:  # timeout, lỗi mạng...
            raise AnthropicCallError(f"Không gọi được Anthropic API: {exc}") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        text = "".join(block.text for block in message.content if getattr(block, "type", None) == "text")

        return LLMResponse(
            text=text,
            model=message.model,
            input_tokens=getattr(message.usage, "input_tokens", None),
            output_tokens=getattr(message.usage, "output_tokens", None),
            latency_ms=latency_ms,
            stop_reason=message.stop_reason,
        )
