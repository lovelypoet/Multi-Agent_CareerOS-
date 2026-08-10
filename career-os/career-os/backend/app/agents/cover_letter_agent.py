"""Cover letter agent — soạn thư xin việc dựa trên resume + job description + kết quả matching.

Module PRIVATE. Backend chỉ gọi nó qua `BaseAgent` (xem app/core/agent_contract.py) và lấy
instance qua `app.core.agent_registry.get_agent("cover_letter_agent")` — không file public nào
import trực tiếp file này.

Quyết định quan trọng — LUÔN dùng Claude, KHÔNG theo `settings.llm_provider` toàn cục: khác với
`matching_agent` (cho phép chọn `anthropic`/`ollama`/`ollama_ensemble`), agent này LUÔN khởi tạo
`AnthropicClient()` trực tiếp, bất kể `LLM_PROVIDER` đang set gì cho toàn hệ thống. Lý do: đã có
bằng chứng thật (xem `docs/hybrid-model-journey.md` mục 2, `prompts/matching_v1_ollama.md`) rằng
model local nhỏ có xu hướng bịa số liệu cụ thể (ví dụ "thiếu 2 năm" không có trong CV) khi dùng
reasoning tự do/few-shot. Với `matching_agent`, hậu quả của lỗi đó chỉ là 1 điểm số sai — có cơ
chế `needs_review` (ensemble 2 model) chặn lại khi phát hiện bất đồng. Với cover letter, hậu quả
là nội dung sai gửi thẳng ra ngoài cho nhà tuyển dụng thật, và không có ensemble kiểm tra chéo nào
phù hợp cho văn xuôi tự do (không có `verdict` để so sánh đồng thuận/bất đồng như kết quả matching
có cấu trúc). Tần suất tạo cover letter thấp hơn nhiều matching (chỉ khi approve, không phải mọi
job fetch) nên chi phí tổng thể vẫn nhỏ dù luôn dùng Claude.
"""

from __future__ import annotations

import time

from pydantic import ValidationError

from app.agents.json_parsing import parse_agent_json
from app.agents.prompt_loader import load_prompt
from app.core.agent_contract import (
    AgentContext,
    AgentExecutionError,
    AgentResult,
    AgentRunLog,
    BaseAgent,
)
from app.integrations.anthropic import AnthropicCallError, AnthropicClient
from app.integrations.llm_client import LLMClient
from app.schemas.cover_letter import CoverLetterOutput

AGENT_NAME = "cover_letter_agent"
PROMPT_VERSION = "cover_letter_v1"


class CoverLetterAgent(BaseAgent):
    name = AGENT_NAME

    def __init__(self, client: LLMClient | None = None) -> None:
        # KHÔNG đọc settings.llm_provider — luôn Anthropic, xem docstring module ở trên. `client`
        # chỉ tồn tại để tiêm client giả trong test, không phải để chọn provider.
        self._client = client or AnthropicClient()
        self._prompt = load_prompt(PROMPT_VERSION)

    async def run(self, context: AgentContext) -> AgentResult:
        # `match_context` truyền qua `metadata` (đã có sẵn trong AgentContext cho đúng mục đích
        # này) — API layer build chuỗi tóm tắt từ match_result mới nhất, agent không tự query DB.
        match_context = context.metadata.get("match_context", "")

        user_prompt = self._prompt.render_user_prompt(
            resume_text=context.resume_text,
            job_description_text=context.job_description_text,
            match_context=match_context,
        )

        def _log(
            *,
            model: str | None,
            latency_ms: int,
            input_tokens: int | None = None,
            output_tokens: int | None = None,
            output: dict | None = None,
            error: str | None = None,
        ) -> AgentRunLog:
            return AgentRunLog(
                agent_name=self.name,
                prompt_version=self._prompt.version,
                model=model,
                latency_ms=latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                output=output,
                error=error,
            )

        started = time.perf_counter()
        try:
            response = await self._client.complete(
                system=self._prompt.system_prompt,
                user_content=user_prompt,
                response_schema=CoverLetterOutput.model_json_schema(),
            )
        except AnthropicCallError as exc:
            elapsed = int((time.perf_counter() - started) * 1000)
            client_model = getattr(self._client, "model", None)
            log = _log(model=client_model, latency_ms=elapsed, error=str(exc))
            raise AgentExecutionError(str(exc), [log])

        try:
            payload = parse_agent_json(response.text)
        except ValueError as exc:
            error = f"{exc} | raw_output_head={response.text[:500]!r}"
            log = _log(
                model=response.model,
                latency_ms=response.latency_ms,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                error=error,
            )
            raise AgentExecutionError(error, [log])

        try:
            output = CoverLetterOutput.model_validate(payload)
        except ValidationError as exc:
            error = f"Output sai schema: {exc.errors()} | payload={payload!r}"[:2000]
            log = _log(
                model=response.model,
                latency_ms=response.latency_ms,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                output=payload,
                error=error,
            )
            raise AgentExecutionError(error, [log])

        validated = output.model_dump()
        log = _log(
            model=response.model,
            latency_ms=response.latency_ms,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            output=validated,
        )
        return AgentResult(output=validated, run_logs=[log], needs_review=False)
