"""Script SO SÁNH chất lượng output giữa Claude (Anthropic) và local model (Ollama) trên
các test case tham khảo (`prompts/reference_cases.py`) — phủ đủ 4 dải điểm
(strong/good/partial/weak_match).

TẠM THỜI — không phải 1 phần cố định của hệ thống, có thể xoá sau khi dùng xong. Chạy tay:

    cd backend && python -m app.scripts.compare_providers

Gọi `client.complete()` trực tiếp (không qua `MatchingAgent.run()`) để thấy được RAW text
model trả về trước khi qua bất kỳ bước fallback nào — nếu đi qua `MatchingAgent.run()`, việc
"JSON có hợp lệ ngay lần đầu hay phải strip code fence" sẽ bị che mất vì hàm đó tự xử lý nội
bộ và chỉ trả về kết quả cuối cùng.

Mỗi case chạy nhiều lần (REPEATS) để kiểm tra tính ổn định, không chỉ tin 1 lần chạy.

Quyết định có đặt LLM_PROVIDER=ollama làm mặc định hay không dựa trên kết quả in ra —
KHÔNG tự động đặt, đây là quyết định của người dùng.
"""

from __future__ import annotations

import asyncio
import json
import sys

from pydantic import ValidationError

from app.agents.matching_agent import PROMPT_VERSION_BY_PROVIDER, MatchingAgent, parse_agent_json
from app.agents.prompt_loader import load_prompt
from app.core.agent_contract import AgentContext, AgentExecutionError
from app.integrations.anthropic import AnthropicCallError, AnthropicClient, AnthropicConfigError
from app.integrations.ollama_client import OllamaCallError, OllamaClient
from app.prompts.reference_cases import ALL_CASES, ReferenceCase
from app.schemas.match import MatchOutput

REPEATS = 3


async def _run_once(case: ReferenceCase, client, provider: str) -> dict[str, object]:
    # Mỗi provider đọc đúng prompt của mình — Claude vẫn matching_v1.md nguyên bản, Ollama
    # dùng bản có few-shot (matching_v1_ollama.md), khớp đúng thứ MatchingAgent thật sẽ dùng.
    prompt = load_prompt(PROMPT_VERSION_BY_PROVIDER[provider])
    user_prompt = prompt.render_user_prompt(
        resume_text=case.resume_text, job_description_text=case.job_description_text
    )

    try:
        response = await client.complete(system=prompt.system_prompt, user_content=user_prompt)
    except (AnthropicCallError, OllamaCallError) as exc:
        return {"error": str(exc)}

    raw_text = response.text
    try:
        json.loads(raw_text.strip())
        valid_json_on_first_try = True
    except json.JSONDecodeError:
        valid_json_on_first_try = False

    try:
        payload = parse_agent_json(raw_text)
        output = MatchOutput.model_validate(payload)
    except (ValueError, ValidationError) as exc:
        return {
            "error": f"Parse/validate thất bại: {exc}",
            "raw_text_head": raw_text[:300],
            "latency_ms": response.latency_ms,
        }

    return {
        "score": output.score,
        "verdict": output.verdict,
        "reasoning": output.reasoning,
        "matched_requirements": output.matched_requirements,
        "missing_requirements": output.missing_requirements,
        "valid_json_on_first_try": valid_json_on_first_try,
        "latency_ms": response.latency_ms,
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
    }


def _print_run(case: ReferenceCase, run_index: int, result: dict[str, object]) -> None:
    print(f"\n  [Lần {run_index}]")
    if "error" in result:
        print(f"    LỖI: {result['error']}")
        if "raw_text_head" in result:
            print(f"    raw output (300 ký tự đầu): {result['raw_text_head']!r}")
        return

    score = result["score"]
    verdict = result["verdict"]
    lo, hi = case.expected_score_range
    in_range = lo <= score <= hi
    verdict_ok = verdict == case.expected_verdict

    print(f"    score: {score}  [{'trong khoang ky vong' if in_range else f'!! LECH KHOI {lo}-{hi}'}]")
    print(f"    verdict: {verdict}  [{'dung ky vong' if verdict_ok else f'!! KHONG PHAI {case.expected_verdict}'}]")
    print(f"    JSON hop le ngay lan dau: {'co' if result['valid_json_on_first_try'] else 'KHONG - phai qua fallback'}")
    print(f"    matched_requirements: {result['matched_requirements']}")
    print(f"    missing_requirements: {result['missing_requirements']}")
    print(f"    reasoning: {result['reasoning']}")
    print(f"    latency_ms: {result['latency_ms']}, input_tokens: {result['input_tokens']}, output_tokens: {result['output_tokens']}")


async def _run_case_on_provider(case: ReferenceCase, label: str, provider: str, client_factory) -> None:
    print(f"\n--- {case.label} | {label} | kỳ vọng score {case.expected_score_range[0]}-{case.expected_score_range[1]}, verdict={case.expected_verdict} ---")
    try:
        client = client_factory()
    except AnthropicConfigError as exc:
        print(f"  Không khởi tạo được client: {exc}")
        return

    for i in range(1, REPEATS + 1):
        result = await _run_once(case, client, provider)
        _print_run(case, i, result)


async def _run_ensemble_once(case: ReferenceCase) -> dict[str, object]:
    """Chạy 1 case qua `MatchingAgent` thật ở chế độ ensemble (2 model độc lập + reconciliation)
    — KHÔNG gọi client trực tiếp như `_run_once`, vì logic reconciliation (lấy model điểm thấp
    hơn) nằm trong `MatchingAgent.run()`, không nên viết lại ở đây.
    """
    agent = MatchingAgent(
        ensemble_clients=[
            OllamaClient(model="qwen2.5:7b"),
            OllamaClient(model="llama3.1:8b"),
        ]
    )
    context = AgentContext(resume_text=case.resume_text, job_description_text=case.job_description_text)

    try:
        result = await agent.run(context)
    except AgentExecutionError as exc:
        return {"error": str(exc), "per_model": [(log.model, None, log.error) for log in exc.run_logs]}

    per_model = [(log.model, log.output, log.error) for log in result.run_logs]
    return {
        "score": result.output["score"],
        "verdict": result.output["verdict"],
        "reasoning": result.output["reasoning"],
        "matched_requirements": result.output["matched_requirements"],
        "missing_requirements": result.output["missing_requirements"],
        "per_model": per_model,
    }


def _print_ensemble_run(case: ReferenceCase, run_index: int, result: dict[str, object]) -> None:
    print(f"\n  [Lần {run_index}]")

    for model, output, error in result["per_model"]:
        if error is not None:
            print(f"    {model}: LỖI - {error}")
        else:
            print(f"    {model}: score={output['score']}, verdict={output['verdict']}")

    if "error" in result:
        print(f"    => CẢ HAI LỖI: {result['error']}")
        return

    scores = [output["score"] for _, output, error in result["per_model"] if error is None]
    verdicts = [output["verdict"] for _, output, error in result["per_model"] if error is None]
    agreement = "ĐỒNG THUẬN" if len(set(verdicts)) == 1 else "BẤT ĐỒNG"
    print(f"    -> {agreement} (scores: {scores})")

    score = result["score"]
    verdict = result["verdict"]
    lo, hi = case.expected_score_range
    in_range = lo <= score <= hi
    verdict_ok = verdict == case.expected_verdict
    print(f"    Kết quả cuối (sau reconciliation): score={score} [{'trong khoang ky vong' if in_range else f'!! LECH KHOI {lo}-{hi}'}], verdict={verdict} [{'dung ky vong' if verdict_ok else f'!! KHONG PHAI {case.expected_verdict}'}]")
    print(f"    reasoning: {result['reasoning']}")


async def run_ensemble_comparison() -> None:
    """So sánh riêng cho chế độ ollama_ensemble — chạy 4 case cũ, mỗi case REPEATS lần."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("=== Ensemble (qwen2.5:7b + llama3.1:8b) trên các test case tham khảo ===")
    print(f"Mỗi case chạy {REPEATS} lần để kiểm tra tính ổn định.\n")

    for case in ALL_CASES:
        print(f"\n--- {case.label} | kỳ vọng score {case.expected_score_range[0]}-{case.expected_score_range[1]}, verdict={case.expected_verdict} ---")
        for i in range(1, REPEATS + 1):
            result = await _run_ensemble_once(case)
            _print_ensemble_run(case, i, result)


async def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("=== So sánh Claude vs Ollama trên các test case tham khảo ===")
    print(f"Mỗi case chạy {REPEATS} lần để kiểm tra tính ổn định.\n")

    for case in ALL_CASES:
        await _run_case_on_provider(case, "Claude (Anthropic)", "anthropic", AnthropicClient)
        await _run_case_on_provider(case, "Ollama (qwen2.5:7b)", "ollama", OllamaClient)

    print("\n=== Hết. Quyết định có đặt LLM_PROVIDER=ollama làm mặc định là quyết định của bạn. ===")


if __name__ == "__main__":
    asyncio.run(main())
