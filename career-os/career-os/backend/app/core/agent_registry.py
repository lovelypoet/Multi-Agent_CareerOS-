"""Cầu nối public → private.

Đây là file public DUY NHẤT được phép biết tên module private, và nó chỉ biết tên dưới dạng
chuỗi, import lazy lúc runtime. Nhờ vậy:
  - `api/` không import `app.agents.*` trực tiếp;
  - nếu folder private bị loại bỏ khi public repo, app vẫn khởi động bình thường và chỉ
    trả lỗi rõ ràng khi endpoint thực sự cần agent.
"""

from __future__ import annotations

from functools import lru_cache
from importlib import import_module

from app.core.agent_contract import AgentUnavailableError, BaseAgent

# tên agent -> "module:ClassName" (module private, import lazy)
_AGENT_PATHS: dict[str, str] = {
    "matching_agent": "app.agents.matching_agent:MatchingAgent",
    "cover_letter_agent": "app.agents.cover_letter_agent:CoverLetterAgent",
    "scam_detection_agent": "app.agents.scam_detection_agent:ScamDetectionAgent",
    "email_classifier_agent": "app.agents.email_classifier_agent:EmailClassifierAgent",
    "cv_extraction_agent": "app.agents.cv_extraction_agent:CVExtractionAgent",
}


@lru_cache
def get_agent(name: str) -> BaseAgent:
    """Trả về instance đã cache — mỗi request không dựng lại HTTP client mới.

    `lru_cache` không cache exception, nên nếu lần đầu lỗi do thiếu API key thì sau khi điền key
    và restart/gọi lại vẫn khởi tạo lại bình thường.
    """
    try:
        path = _AGENT_PATHS[name]
    except KeyError as exc:
        raise AgentUnavailableError(f"Chưa đăng ký agent nào tên '{name}'.") from exc

    module_path, class_name = path.split(":")
    try:
        module = import_module(module_path)
    except ImportError as exc:
        raise AgentUnavailableError(
            f"Agent '{name}' không khả dụng: thiếu module private '{module_path}'. "
            "Bản build này có thể đã loại bỏ các folder private (agents/, prompts/, workflows/)."
        ) from exc

    agent_class = getattr(module, class_name)
    return agent_class()
