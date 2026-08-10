"""Matching agent — chấm mức độ phù hợp giữa resume và job description.

Module PRIVATE. Backend chỉ gọi nó qua `BaseAgent` (xem app/core/agent_contract.py) và lấy
instance qua `app.core.agent_registry.get_agent("matching_agent")` — không file public nào
import trực tiếp file này.

3 chế độ, chọn qua `settings.llm_provider`:
- "anthropic": gọi Claude 1 lần, dùng `matching_v1.md`.
- "ollama": gọi 1 model local 1 lần, dùng `matching_v1_ollama.md` (bản có few-shot).
- "ollama_ensemble": gọi 2 model local ĐỘC LẬP (kiến trúc khác nhau) cùng `matching_v1.md`
  GỐC (không few-shot — 2 model phải cùng xuất phát điểm để bất đồng phản ánh đúng khác biệt
  reasoning, không phải do prompt khác nhau). ĐỒNG THUẬN (cùng verdict) → lấy kết quả của
  model điểm THẤP hơn (thận trọng hơn) làm kết quả cuối. BẤT ĐỒNG (khác verdict, bất kỳ mức
  nào) → KHÔNG tự chọn, `output=None`, `needs_review=True` — dữ liệu test cho thấy đồng
  thuận/bất đồng dự đoán đúng/sai tốt hơn hẳn việc luôn lấy điểm thấp hơn. Không phải Agent
  Router — không có logic "chọn model theo loại task", chỉ 1 task chạy qua 2 model để kiểm
  tra chéo.
"""

from __future__ import annotations

import json
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
from app.schemas.match import MatchOutput

# Claude dùng bản gốc; Ollama (1 model) dùng bản có thêm few-shot examples (xem
# prompts/matching_v1_ollama.md) để sửa lỗi calibration đã quan sát được ở model local.
# ollama_ensemble KHÔNG dùng bảng này — luôn ép về "matching_v1" gốc, xem __init__.
PROMPT_VERSION_BY_PROVIDER = {
    "anthropic": "matching_v1",
    "ollama": "matching_v1_ollama",
}
AGENT_NAME = "matching_agent"

# `parse_agent_json` sống ở app.agents.json_parsing (dùng chung với cover_letter_agent) — import
# lại vào đây để `from app.agents.matching_agent import parse_agent_json` (test cũ) vẫn hoạt động.
__all__ = ["MatchingAgent", "parse_agent_json", "PROMPT_VERSION_BY_PROVIDER", "AGENT_NAME"]


def _build_default_client(settings) -> LLMClient:
    """Chọn provider cho chế độ 1 model — đổi qua .env, không sửa code."""
    if settings.llm_provider == "ollama":
        return OllamaClient()
    return AnthropicClient()


def _build_ensemble_clients(settings) -> list[LLMClient]:
    """2 model ĐỘC LẬP, kiến trúc khác nhau (Qwen vs Llama) — 2 model cùng họ dễ mắc chung lỗi,
    không phát hiện được gì khi kiểm tra chéo."""
    return [
        OllamaClient(model=settings.ollama_model),
        OllamaClient(model=settings.ollama_secondary_model),
    ]


class MatchingAgent(BaseAgent):
    name = AGENT_NAME

    def __init__(
        self,
        client: LLMClient | None = None,
        ensemble_clients: list[LLMClient] | None = None,
    ) -> None:
        settings = get_settings()
        # `ensemble_clients` cho phép tiêm 2 client giả khi test ensemble mode; `client` giữ
        # nguyên hành vi cũ (tiêm 1 client giả cho chế độ 1 model) — không đổi API hiện có.
        is_ensemble = ensemble_clients is not None or (
            client is None and settings.llm_provider == "ollama_ensemble"
        )

        if is_ensemble:
            self._clients = ensemble_clients or _build_ensemble_clients(settings)
            # Ensemble LUÔN dùng matching_v1.md gốc cho cả 2 model, không dùng bản few-shot dù
            # đang chạy Ollama — 2 model phải cùng xuất phát điểm để bất đồng giữa chúng phản
            # ánh đúng khác biệt reasoning, không phải do prompt khác nhau.
            self._prompt = load_prompt("matching_v1")
        else:
            self._clients = [client or _build_default_client(settings)]
            self._prompt = load_prompt(PROMPT_VERSION_BY_PROVIDER[settings.llm_provider])

        self._ensemble = is_ensemble

    async def run(self, context: AgentContext) -> AgentResult:
        user_prompt = self._prompt.render_user_prompt(
            resume_text=context.resume_text,
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

        # Chạy TỪNG client tuần tự, thu (output đã validate | None, run_log) cho mỗi client.
        # 1 client lỗi KHÔNG cản các client còn lại — ensemble: 1 model lỗi vẫn dùng được kết
        # quả của model kia; chế độ 1 model: list chỉ có 1 phần tử, hành vi y hệt trước đây.
        outcomes: list[tuple[dict[str, Any] | None, AgentRunLog]] = []

        for client in self._clients:
            client_model = getattr(client, "model", None)
            started = time.perf_counter()
            try:
                response = await client.complete(
                    system=self._prompt.system_prompt,
                    user_content=user_prompt,
                    response_schema=MatchOutput.model_json_schema(),
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
                output = MatchOutput.model_validate(payload)
            except ValidationError as exc:
                error = f"Output sai schema: {exc.errors()} | payload={json.dumps(payload)[:500]}"
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
            # Chế độ 1 model: đúng 1 lỗi, message y hệt hành vi cũ. Ensemble: CẢ HAI đều lỗi.
            combined_message = "; ".join(log.error for log in run_logs if log.error) or "Agent lỗi không rõ nguyên nhân."
            raise AgentExecutionError(combined_message, run_logs)

        # Reconciliation — chỉ có ý nghĩa khi ≥2 model đều thành công (ensemble). Chế độ 1
        # model: successful chỉ có 1 phần tử, dùng thẳng, không có gì để "bất đồng".
        if len(successful) > 1:
            verdicts = {out["verdict"] for out, _ in successful}
            if len(verdicts) > 1:
                # Bất đồng verdict — KHÔNG tự chọn 1 bên (không phải "bất đồng nhẹ/nặng", bất
                # kỳ khác biệt verdict nào cũng tính). Không có output chính thức để lưu; cả 2
                # run_log vẫn được trả về đầy đủ để caller ghi agent_runs bình thường. Đây
                # KHÔNG phải lỗi — cả 2 model đều chạy đúng, chỉ là không đồng thuận.
                return AgentResult(output=None, run_logs=run_logs, needs_review=True)

            # Đồng thuận (cùng verdict): lấy TOÀN BỘ output của model có score THẤP hơn — thận
            # trọng hơn, không phải chỉ lấy con số rồi ghép reasoning của model kia. Hòa thì lấy
            # result đầu tiên (min() ổn định theo thứ tự danh sách khi bằng nhau).
            chosen_output, _ = min(successful, key=lambda pair: pair[0]["score"])
        else:
            chosen_output, _ = successful[0]

        return AgentResult(output=chosen_output, run_logs=run_logs, needs_review=False)
