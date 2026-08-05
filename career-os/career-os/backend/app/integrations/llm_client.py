"""Interface chung cho mọi LLM provider — `AnthropicClient` (Claude) và `OllamaClient`
(local) đều implement đúng interface này, để `matching_agent.py` gọi model nào cũng qua
cùng 1 shape, không cần biết chi tiết provider.

`LLMResponse` từng định nghĩa trong `anthropic.py` — chuyển sang đây để dùng chung cho mọi
provider, không phải giả định "response của Anthropic" nữa.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class LLMResponse:
    """Kết quả 1 lần gọi model, kèm số liệu để ghi vào `agent_runs`."""

    text: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int
    stop_reason: str | None = None


class LLMClient(Protocol):
    async def complete(
        self,
        *,
        system: str,
        user_content: str,
        max_tokens: int | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse: ...
