"""Đọc prompt từ file .md trong `app/prompts/` — KHÔNG hardcode prompt trong code.

Vì sao phải parse cẩn thận: bên trong section "User Prompt Template" có một khối code fence,
mà nội dung khối đó lại chứa các dòng bắt đầu bằng `## ` (## Resume / CV của ứng viên, ...).
Nếu tách section bằng cách quét mọi dòng `## ` thì template sẽ bị cắt vụn. Do đó parser phải
bám theo trạng thái đang ở trong hay ngoài code fence.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"

RESUME_PLACEHOLDER = "{resume_text}"
JOB_PLACEHOLDER = "{job_description_text}"


class PromptFileError(RuntimeError):
    """File prompt thiếu section bắt buộc hoặc sai định dạng."""


@dataclass(slots=True)
class LoadedPrompt:
    version: str
    system_prompt: str
    user_template: str

    def render_user_prompt(self, *, resume_text: str, job_description_text: str) -> str:
        """Thay placeholder bằng `replace` chứ không phải `str.format`.

        Resume và JD là text tự do, hoàn toàn có thể chứa dấu `{` `}` (ví dụ đoạn code trong CV).
        `str.format` sẽ vỡ hoặc hiểu nhầm chúng thành field name.
        """
        return self.user_template.replace(RESUME_PLACEHOLDER, resume_text).replace(
            JOB_PLACEHOLDER, job_description_text
        )


def _split_sections(markdown: str) -> dict[str, list[str]]:
    """Tách file thành {tiêu đề H2: các dòng nội dung}, bỏ qua heading nằm trong code fence."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    in_fence = False

    for line in markdown.splitlines():
        stripped = line.strip()

        if stripped.startswith("```"):
            in_fence = not in_fence
            if current is not None:
                sections[current].append(line)
            continue

        if not in_fence and stripped.startswith("## "):
            current = stripped[3:].strip()
            sections.setdefault(current, [])
            continue

        if current is not None:
            sections[current].append(line)

    return sections


def _clean(lines: list[str]) -> str:
    """Bỏ dấu phân cách `---` ở cuối section và khoảng trắng thừa."""
    while lines and lines[-1].strip() in ("", "---"):
        lines.pop()
    while lines and not lines[0].strip():
        lines.pop(0)
    return "\n".join(lines).strip()


def _first_fenced_block(lines: list[str]) -> str | None:
    """Lấy nội dung khối code fence đầu tiên trong section."""
    block: list[str] = []
    in_fence = False
    for line in lines:
        if line.strip().startswith("```"):
            if in_fence:
                return "\n".join(block).strip()
            in_fence = True
            continue
        if in_fence:
            block.append(line)
    return None


@lru_cache
def load_prompt(version: str) -> LoadedPrompt:
    """Đọc `app/prompts/{version}.md`. `version` cũng chính là `prompt_version` ghi vào DB."""
    path = PROMPTS_DIR / f"{version}.md"
    if not path.is_file():
        raise PromptFileError(f"Không tìm thấy file prompt: {path}")

    sections = _split_sections(path.read_text(encoding="utf-8"))

    if "System Prompt" not in sections:
        raise PromptFileError(f"{path.name} thiếu section '## System Prompt'.")
    if "User Prompt Template" not in sections:
        raise PromptFileError(f"{path.name} thiếu section '## User Prompt Template'.")

    # "Output Format" là chỉ dẫn dành cho model, nên nó thuộc system prompt.
    system_parts = [_clean(list(sections["System Prompt"]))]
    if "Output Format" in sections:
        system_parts.append("## Output Format\n\n" + _clean(list(sections["Output Format"])))
    system_prompt = "\n\n".join(part for part in system_parts if part)

    user_template = _first_fenced_block(sections["User Prompt Template"])
    if not user_template:
        raise PromptFileError(
            f"{path.name}: section '## User Prompt Template' phải chứa 1 khối code fence."
        )

    for placeholder in (RESUME_PLACEHOLDER, JOB_PLACEHOLDER):
        if placeholder not in user_template:
            raise PromptFileError(f"{path.name}: user template thiếu placeholder {placeholder}.")

    return LoadedPrompt(
        version=version,
        system_prompt=system_prompt,
        user_template=user_template,
    )
