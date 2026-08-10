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


class PromptFileError(RuntimeError):
    """File prompt thiếu section bắt buộc hoặc sai định dạng."""


@dataclass(slots=True)
class LoadedPrompt:
    version: str
    system_prompt: str
    user_template: str

    def render_user_prompt(self, **replacements: str) -> str:
        """Generic — nhận bất kỳ số placeholder nào (`resume_text`, `job_description_text`,
        `match_context`, ...), dùng `replace` chứ không phải `str.format`.

        Resume/JD/match_context là text tự do, hoàn toàn có thể chứa dấu `{` `}` (ví dụ đoạn
        code trong CV). `str.format` sẽ vỡ hoặc hiểu nhầm chúng thành field name.

        BUG ĐÃ VERIFY ở bản cũ (chỉ nhận đúng `resume_text`/`job_description_text` qua tham số
        tên cố định): gọi hàm với placeholder thứ 3 không có trong chữ ký (vd. `match_context`
        cho cover letter) không hề báo lỗi — placeholder đó chỉ đơn giản không được thay thế,
        giữ nguyên dạng `{match_context}` trong chuỗi gửi thẳng cho LLM. `**kwargs` sửa tận gốc:
        thay bao nhiêu key được truyền vào thì thay bấy nhiêu, không giới hạn cứng 2 tham số.
        """
        rendered = self.user_template
        for key, value in replacements.items():
            rendered = rendered.replace("{" + key + "}", value)
        return rendered


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

    # KHÔNG kiểm tra placeholder cụ thể nào ở đây nữa. BUG ĐÃ VERIFY 2 LẦN LIÊN TIẾP: bản đầu
    # bắt buộc CẢ {resume_text} lẫn {job_description_text} (viết từ lúc chỉ có matching_agent,
    # luôn cần cả 2); sửa lần 1 chỉ còn bắt buộc {job_description_text} khi thêm
    # scam_detection_agent (không cần resume) — tưởng đã tổng quát nhưng vẫn hardcode 1 giả định
    # mới ("mọi agent đều có job_description_text"). Giờ thêm email_classifier_agent (không có
    # cả 2, chỉ có {sender}/{subject}/{body_text}) chứng minh giả định đó cũng sai — KHÔNG còn
    # placeholder nào chung cho MỌI agent để bắt buộc ở tầng loader. An toàn thật sự nằm ở test
    # riêng cho từng file prompt (xem `tests/test_prompt_and_parsing.py`), không phải 1 rule
    # chung đoán trước ở đây — mỗi lần "tổng quát hoá" bằng cách đổi sang 1 placeholder cụ thể
    # khác lại chỉ trì hoãn cùng 1 lỗi sang agent tiếp theo.
    return LoadedPrompt(
        version=version,
        system_prompt=system_prompt,
        user_template=user_template,
    )
