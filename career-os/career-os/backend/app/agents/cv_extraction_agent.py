"""CV extraction agent — tự rút `domains`/`key_skills` từ resume, dùng bổ sung (không thay thế)
bộ lọc từ khóa tĩnh `workers/relevance_keywords.py` (xem `workers/fetch_jobs.py`).

Module PRIVATE. Backend chỉ gọi nó qua `BaseAgent` (xem app/core/agent_contract.py) và lấy
instance qua `app.core.agent_registry.get_agent("cv_extraction_agent")` — không file public nào
import trực tiếp file này.

Quyết định quan trọng — hỗ trợ `anthropic`/`ollama` (đơn model), KHÔNG BAO GIỜ chạy
`ollama_ensemble` dù `settings.llm_provider` đang set giá trị đó: agent thứ 2 (sau
`cover_letter_agent`) cần "lách" khỏi hành vi ensemble mặc định, nhưng theo cách KHÁC —
`cover_letter_agent` khoá cứng Anthropic, bỏ qua `settings.llm_provider` hoàn toàn; agent này vẫn
tôn trọng lựa chọn anthropic/ollama của người dùng, chỉ bỏ qua riêng phần ensemble. Lý do: trích
xuất cho ra 1 DANH SÁCH tự do (`domains`/`key_skills`), so sánh "2 danh sách có đồng thuận không"
giữa 2 model không có tiêu chí rõ ràng/có ý nghĩa như so sánh 2 giá trị phân loại (`verdict` ở
matching, `risk_level` ở scam detection). Khi `settings.llm_provider == "ollama_ensemble"`, agent
này CHỈ dùng 1 trong 2 model đã cấu hình (`settings.ollama_model`) — KHÔNG cố "ensemble hoá" theo
cách nào khác.

Ghi chú kiến trúc (không bắt buộc sửa ngay, xem prompt Phase 3 việc #4 mục 9): nếu có agent thứ 3
cũng cần kiểu "lách" ensemble tương tự, cân nhắc gom thành 1 helper dùng chung trong `core/`
(vd. `resolve_single_client(settings, force_provider=None)`) thay vì mỗi agent tự viết lại. Hiện
tại mới có 2 trường hợp (khác nhau về cách "lách"), chưa đáng trừu tượng hoá.
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
from app.core.config import get_settings
from app.integrations.anthropic import AnthropicCallError, AnthropicClient
from app.integrations.llm_client import LLMClient
from app.integrations.ollama_client import OllamaCallError, OllamaClient
from app.schemas.cv_extraction import CVExtractionOutput

AGENT_NAME = "cv_extraction_agent"
PROMPT_VERSION = "cv_extraction_v1"


def _build_client(settings) -> LLMClient:
    """Chọn provider — CHỈ đơn model, không bao giờ ensemble (xem docstring module). Khi
    `llm_provider == "ollama_ensemble"`, dùng `settings.ollama_model` (bỏ qua
    `ollama_secondary_model` hoàn toàn — không có "model thứ 2" nào được gọi ở agent này)."""
    if settings.llm_provider in ("ollama", "ollama_ensemble"):
        return OllamaClient(model=settings.ollama_model)
    return AnthropicClient()


class CVExtractionAgent(BaseAgent):
    name = AGENT_NAME

    def __init__(self, client: LLMClient | None = None) -> None:
        settings = get_settings()
        self._client = client or _build_client(settings)
        self._prompt = load_prompt(PROMPT_VERSION)

    async def run(self, context: AgentContext) -> AgentResult:
        user_prompt = self._prompt.render_user_prompt(resume_text=context.resume_text)

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
                response_schema=CVExtractionOutput.model_json_schema(),
            )
        except (AnthropicCallError, OllamaCallError) as exc:
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
            output = CVExtractionOutput.model_validate(payload)
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
