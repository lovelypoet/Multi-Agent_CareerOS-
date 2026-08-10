"""Email classifier agent — xác định 1 email có liên quan tới quá trình ứng tuyển việc làm của
người dùng hay không, và phân loại theo `category` nếu có.

Module PRIVATE. Backend chỉ gọi nó qua `BaseAgent` (xem app/core/agent_contract.py) và lấy
instance qua `app.core.agent_registry.get_agent("email_classifier_agent")` — không file public
nào import trực tiếp file này.

Tái dùng kiến trúc `matching_agent.py`/`scam_detection_agent.py` — bài toán PHÂN LOẠI có cấu
trúc (`category` đóng vai trò tương tự `verdict`/`risk_level`), dùng được multi-provider
(anthropic/ollama/ollama_ensemble) + ensemble + `needs_review`. Khác `cover_letter_agent`
(luôn Claude-only): Gmail vẫn là nguồn dữ liệu gốc đầy đủ — nếu model phân loại sai, người dùng
vẫn thấy email đó trong Gmail thật, không mất thông tin gì — mức độ nghiêm trọng thấp hơn hẳn
fabrication trong cover letter (gửi ra ngoài cho nhà tuyển dụng thật) hay bỏ sót scam (không có
nguồn đối chiếu nào khác ngoài đánh giá của model).

3 chế độ, chọn qua `settings.llm_provider`, giống matching_agent/scam_detection_agent:
- "anthropic": gọi Claude 1 lần.
- "ollama": gọi 1 model local 1 lần.
- "ollama_ensemble": gọi 2 model local ĐỘC LẬP cùng prompt `email_classification_v1`. ĐỒNG THUẬN
  (cùng `is_relevant` VÀ cùng `category`) → lấy nguyên bản KẾT QUẢ ĐẦU TIÊN trong danh sách client
  — khác `matching_agent` (điểm thấp hơn) và `scam_detection_agent` (nhiều red_flags hơn), ở đây
  KHÔNG có tín hiệu định lượng tự nhiên nào để xếp hạng "thận trọng hơn" giữa 2 kết quả đã đồng ý
  cùng kết luận (không có điểm số, không có danh sách đếm được như red_flags) — lấy kết quả đầu
  tiên là lựa chọn đơn giản, xác định, không bịa thêm 1 tiêu chí xếp hạng không có căn cứ. BẤT
  ĐỒNG (`is_relevant` HOẶC `category` khác nhau) → KHÔNG tự chọn, `output=None`,
  `needs_review=True` — tái dùng nguyên contract `AgentResult`/`AgentRunLog` đã có.

KHÔNG có prompt variant riêng theo provider — chưa có bằng chứng thật nào về lỗi calibration của
model local trên bài toán này, không over-engineer khi chưa cần (giống lý do ở scam_detection_agent).
"""

from __future__ import annotations

import time
from typing import Any

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
from app.schemas.email_notification import EmailClassificationOutput

AGENT_NAME = "email_classifier_agent"
PROMPT_VERSION = "email_classification_v1"


def _build_default_client(settings) -> LLMClient:
    """Chọn provider cho chế độ 1 model — đổi qua .env, không sửa code (giống matching_agent)."""
    if settings.llm_provider == "ollama":
        return OllamaClient()
    return AnthropicClient()


def _build_ensemble_clients(settings) -> list[LLMClient]:
    """2 model ĐỘC LẬP, kiến trúc khác nhau (Qwen vs Llama) — giống hệt lý do ở matching_agent."""
    return [
        OllamaClient(model=settings.ollama_model),
        OllamaClient(model=settings.ollama_secondary_model),
    ]


class EmailClassifierAgent(BaseAgent):
    name = AGENT_NAME

    def __init__(
        self,
        client: LLMClient | None = None,
        ensemble_clients: list[LLMClient] | None = None,
    ) -> None:
        settings = get_settings()
        is_ensemble = ensemble_clients is not None or (
            client is None and settings.llm_provider == "ollama_ensemble"
        )

        if is_ensemble:
            self._clients = ensemble_clients or _build_ensemble_clients(settings)
        else:
            self._clients = [client or _build_default_client(settings)]

        self._prompt = load_prompt(PROMPT_VERSION)
        self._ensemble = is_ensemble

    async def run(self, context: AgentContext) -> AgentResult:
        # Không dùng resume_text/job_description_text — nội dung email truyền qua metadata
        # (đã có sẵn trong AgentContext cho đúng mục đích này, xem cover_letter_agent tiền lệ).
        sender = context.metadata.get("sender", "")
        subject = context.metadata.get("subject", "")
        body_text = context.metadata.get("body_text", "")

        user_prompt = self._prompt.render_user_prompt(
            sender=sender, subject=subject, body_text=body_text
        )

        def _log(
            *,
            model: str | None,
            latency_ms: int,
            input_tokens: int | None = None,
            output_tokens: int | None = None,
            output: dict[str, Any] | None = None,
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

        outcomes: list[tuple[dict[str, Any] | None, AgentRunLog]] = []

        for client in self._clients:
            client_model = getattr(client, "model", None)
            started = time.perf_counter()
            try:
                response = await client.complete(
                    system=self._prompt.system_prompt,
                    user_content=user_prompt,
                    response_schema=EmailClassificationOutput.model_json_schema(),
                )
            except (AnthropicCallError, OllamaCallError) as exc:
                elapsed = int((time.perf_counter() - started) * 1000)
                outcomes.append((None, _log(model=client_model, latency_ms=elapsed, error=str(exc))))
                continue

            try:
                payload = parse_agent_json(response.text)
            except ValueError as exc:
                error = f"{exc} | raw_output_head={response.text[:500]!r}"
                outcomes.append(
                    (
                        None,
                        _log(
                            model=response.model,
                            latency_ms=response.latency_ms,
                            input_tokens=response.input_tokens,
                            output_tokens=response.output_tokens,
                            error=error,
                        ),
                    )
                )
                continue

            try:
                output = EmailClassificationOutput.model_validate(payload)
            except ValidationError as exc:
                error = f"Output sai schema: {exc.errors()} | payload={payload!r}"[:2000]
                outcomes.append(
                    (
                        None,
                        _log(
                            model=response.model,
                            latency_ms=response.latency_ms,
                            input_tokens=response.input_tokens,
                            output_tokens=response.output_tokens,
                            output=payload,
                            error=error,
                        ),
                    )
                )
                continue

            validated = output.model_dump()
            outcomes.append(
                (
                    validated,
                    _log(
                        model=response.model,
                        latency_ms=response.latency_ms,
                        input_tokens=response.input_tokens,
                        output_tokens=response.output_tokens,
                        output=validated,
                    ),
                )
            )

        run_logs = [log for _, log in outcomes]
        successful = [(out, log) for out, log in outcomes if out is not None]

        if not successful:
            combined_message = (
                "; ".join(log.error for log in run_logs if log.error) or "Agent lỗi không rõ nguyên nhân."
            )
            raise AgentExecutionError(combined_message, run_logs)

        if len(successful) > 1:
            # Bất đồng: is_relevant HOẶC category khác nhau — bất kỳ khác biệt nào cũng tính.
            keys = {(out["is_relevant"], out["category"]) for out, _ in successful}
            if len(keys) > 1:
                return AgentResult(output=None, run_logs=run_logs, needs_review=True)

            # Đồng thuận: không có tín hiệu định lượng để xếp "thận trọng hơn" (khác matching/
            # scam) — lấy kết quả đầu tiên, đơn giản và xác định.
            chosen_output, _ = successful[0]
        else:
            chosen_output, _ = successful[0]

        return AgentResult(output=chosen_output, run_logs=run_logs, needs_review=False)
