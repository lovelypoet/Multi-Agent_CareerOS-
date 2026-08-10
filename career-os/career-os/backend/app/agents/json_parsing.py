"""Parse JSON output từ LLM — dùng chung cho mọi agent.

Tách ra từ `matching_agent.py` (logic đã test kỹ ở Phase 0, xem `tests/test_prompt_and_parsing.py`)
để `cover_letter_agent.py` tái dùng nguyên vẹn, không copy-paste lại cùng 1 logic parse.
"""

from __future__ import annotations

import json
import re
from typing import Any

# Bắt cả ```json ... ``` lẫn ``` ... ```
_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _strip_code_fence(text: str) -> str | None:
    """Lấy nội dung bên trong code fence đầu tiên, nếu có."""
    match = _CODE_FENCE_RE.search(text)
    return match.group(1) if match else None


def _extract_json_object(text: str) -> str | None:
    """Cắt lấy đoạn từ `{` đầu tiên tới `}` cuối cùng — cứu trường hợp model thêm lời dẫn."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1]


def parse_agent_json(raw_text: str) -> dict[str, Any]:
    """Parse output của model thành dict.

    Thử `json.loads` trước; nếu lỗi thì strip code fence rồi thử lại. Có thêm 1 lớp cuối cùng
    (cắt từ `{` tới `}`) cho trường hợp model viết thêm câu dẫn ngoài fence. Nếu tất cả đều fail
    thì ném lỗi — KHÔNG trả về dữ liệu rác.
    """
    text = raw_text.strip()
    if not text:
        raise ValueError("Model trả về response rỗng.")

    candidates = [text]
    fenced = _strip_code_fence(text)
    if fenced:
        candidates.append(fenced)
    extracted = _extract_json_object(fenced or text)
    if extracted:
        candidates.append(extracted)

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if not isinstance(parsed, dict):
            last_error = ValueError(f"JSON hợp lệ nhưng không phải object: {type(parsed).__name__}")
            continue
        return parsed

    raise ValueError(f"Không parse được JSON từ output của model: {last_error}")
