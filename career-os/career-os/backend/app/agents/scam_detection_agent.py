"""Scam detection agent — đánh giá 1 job description có dấu hiệu lừa đảo hay không.

Module PRIVATE. Backend chỉ gọi nó qua `BaseAgent` (xem app/core/agent_contract.py) và lấy
instance qua `app.core.agent_registry.get_agent("scam_detection_agent")` — không file public
nào import trực tiếp file này.

Tái dùng kiến trúc `matching_agent.py` gần như nguyên vẹn — đây là bài toán PHÂN LOẠI có cấu
trúc (`risk_level` đóng vai trò tương tự `verdict`), KHÔNG phải sinh văn bản tự do như
`cover_letter_agent`, nên dùng lại được multi-provider + ensemble + `needs_review` đã xây cho
matching — không cần né Claude-only như cover letter.

3 chế độ, chọn qua `settings.llm_provider`, giống matching_agent:
- "anthropic": gọi Claude 1 lần.
- "ollama": gọi 1 model local 1 lần.
- "ollama_ensemble": gọi 2 model local ĐỘC LẬP cùng prompt `scam_detection_v1`. ĐỒNG THUẬN (cùng
  `risk_level` VÀ cùng `is_suspicious`) → lấy bản có SỐ LƯỢNG `red_flags` NHIỀU HƠN (thận trọng
  hơn — nhiều cảnh báo hơn = an toàn hơn cho người dùng, NGƯỢC HƯỚNG với matching dùng "điểm thấp
  hơn": ở matching điểm số càng thấp càng thận trọng, ở đây không có điểm số, tín hiệu thận trọng
  là số lượng cảnh báo). Bằng số lượng thì lấy kết quả đầu tiên (`max()` ổn định theo thứ tự danh
  sách khi bằng nhau, giống cách `min()` đã dùng ở matching). BẤT ĐỒNG (`risk_level` HOẶC
  `is_suspicious` khác nhau) → KHÔNG tự chọn, `output=None`, `needs_review=True` — tái dùng
  nguyên contract `AgentResult`/`AgentRunLog` đã có, không viết lại.

KHÔNG có prompt variant riêng theo provider (khác `matching_agent` có `matching_v1_ollama.md`
few-shot) — chưa có bằng chứng thật nào về lỗi calibration của model local trên bài toán này,
không over-engineer khi chưa cần. Chạy ĐỘC LẬP với `matching_agent` — không chặn, không phụ thuộc
kết quả của nhau (xem `api/jobs.py::analyze_job`, `workers/fetch_jobs.py`).
"""

from __future__ import annotations

from typing import Any

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
from app.schemas.scam_detection import ScamDetectionOutput

AGENT_NAME = "scam_detection_agent"
PROMPT_VERSION = "scam_detection_v1"


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


class ScamDetectionAgent(BaseAgent):
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
        # Không cần resume_text — scam detection chỉ đánh giá bản thân JD, không liên quan CV.
        user_prompt = self._prompt.render_user_prompt(
            job_description_text=context.job_description_text,
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

        # Chạy TỪNG client tuần tự — 1 client lỗi KHÔNG cản các client còn lại, giống hệt
        # matching_agent (xem docstring file đó để biết đầy đủ lý do).
        outcomes: list[tuple[dict[str, Any] | None, AgentRunLog]] = []

        for client in self._clients:
            client_model = getattr(client, "model", None)
            started = time.perf_counter()
            try:
                response = await client.complete(
                    system=self._prompt.system_prompt,
                    user_content=user_prompt,
                    response_schema=ScamDetectionOutput.model_json_schema(),
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
                output = ScamDetectionOutput.model_validate(payload)
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
            # Bất đồng: risk_level HOẶC is_suspicious khác nhau — bất kỳ khác biệt nào cũng tính,
            # không có ngưỡng "bất đồng nhẹ/nặng" (đúng nguyên tắc đã dùng cho verdict ở matching).
            keys = {(out["risk_level"], out["is_suspicious"]) for out, _ in successful}
            if len(keys) > 1:
                return AgentResult(output=None, run_logs=run_logs, needs_review=True)

            # Đồng thuận: lấy bản có SỐ LƯỢNG red_flags nhiều hơn (thận trọng hơn cho người
            # dùng). Hòa thì lấy kết quả đầu tiên (max() ổn định theo thứ tự danh sách khi bằng
            # nhau, giống min() đã dùng ở matching).
            chosen_output, _ = max(successful, key=lambda pair: len(pair[0]["red_flags"]))
        else:
            chosen_output, _ = successful[0]

        return AgentResult(output=chosen_output, run_logs=run_logs, needs_review=False)
