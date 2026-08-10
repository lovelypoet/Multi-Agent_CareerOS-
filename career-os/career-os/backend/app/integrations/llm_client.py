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
    """`response_schema` — JSON Schema (`<Output>.model_json_schema()`) của CHÍNH agent đang
    gọi, PHẢI truyền tường minh mỗi lần gọi `complete()`, KHÔNG có schema mặc định nào ở tầng
    client (đã có tiền lệ hardcode `MatchOutput` gây lỗi cho mọi agent khác dùng chung
    `OllamaClient` — xem `ollama_client.py`). `AnthropicClient` nhận nhưng bỏ qua tham số này
    (Claude không có structured output kiểu grammar-constrained decoding, vẫn dựa vào prompt +
    `parse_agent_json` fallback). `OllamaClient` dùng để ép `format=` — `None` thì không ép gì
    cả, model tự do trả JSON theo hướng dẫn trong prompt."""

    async def complete(
        self,
        *,
        system: str,
        user_content: str,
        max_tokens: int | None = None,
        temperature: float = 0.0,
        response_schema: dict | None = None,
    ) -> LLMResponse: ...
