"""Interface cố định giữa phần PUBLIC (api/, repositories/...) và phần PRIVATE (agents/).

Contract này nằm ở `core/` (public) chứ không nằm trong `agents/` (private) là có chủ đích:
khi tách repo để public FE/BE, ta xoá nguyên 3 folder private (`agents/`, `prompts/`,
`workflows/`) mà phần public vẫn import được và vẫn chạy đúng cấu trúc — chỉ báo lỗi rõ ràng
`AgentUnavailableError` khi có ai đó thực sự gọi agent.

Code public chỉ được biết đúng 3 thứ trong file này: `AgentContext`, `AgentResult`, `BaseAgent`.
Không import chi tiết bên trong `app.agents.*` vào file public nào.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class AgentUnavailableError(RuntimeError):
    """Ném ra khi module private của agent không có mặt trong bản build hiện tại."""


class AgentExecutionError(RuntimeError):
    """Agent chạy nhưng thất bại (API lỗi, output không parse được, output sai schema).

    `run_logs` luôn được điền để caller ghi vào bảng `agent_runs` kể cả khi thất bại — LUÔN là
    1 list (1 phần tử ở chế độ 1 model; nhiều phần tử ở chế độ ensemble khi TẤT CẢ model đều
    lỗi, mỗi model 1 row riêng để xem lại được model nào lỗi gì).
    """

    def __init__(self, message: str, run_logs: list["AgentRunLog"]) -> None:
        super().__init__(message)
        self.run_logs = run_logs


@dataclass(slots=True)
class AgentContext:
    """Input cho một lần chạy agent."""

    resume_text: str
    job_description_text: str
    job_id: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentRunLog:
    """Số liệu quan sát được của 1 lần chạy — map 1-1 với bảng `agent_runs`."""

    agent_name: str
    prompt_version: str
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    output: dict[str, Any] | None = None
    error: str | None = None
    model: str | None = None


@dataclass(slots=True)
class AgentResult:
    """Output của một lần chạy agent — không nhất thiết "thành công" theo nghĩa có kết quả để
    lưu (xem `needs_review`).

    `run_logs` LUÔN là 1 list — 1 phần tử ở chế độ 1 model; ở chế độ ensemble, ghi lại TẤT CẢ
    model đã gọi (không chỉ model được chọn làm kết quả cuối), để xem lại được từng model nói
    gì, không chỉ xem kết quả cuối cùng.

    `output` là `None` khi `needs_review=True` — 2 model (ensemble) đều chạy thành công nhưng
    bất đồng verdict, KHÔNG có kết quả đủ tin cậy để tự chọn 1 bên. Đây KHÔNG phải lỗi
    (`AgentExecutionError`) — cả 2 model đều chạy đúng, chỉ là không đồng thuận.
    """

    output: dict[str, Any] | None
    run_logs: list[AgentRunLog]
    needs_review: bool = False


class BaseAgent(ABC):
    """Interface duy nhất mà backend dùng để gọi bất kỳ agent nào."""

    name: str = "base"

    @abstractmethod
    async def run(self, context: AgentContext) -> AgentResult:  # pragma: no cover - interface
        ...
