"""Test riêng cho phần đọc prompt và parse output — logic dễ vỡ nhất trong agent."""

from __future__ import annotations

import pytest

from app.agents.matching_agent import parse_agent_json
from app.agents.prompt_loader import PromptFileError, load_prompt
from app.schemas.match import MatchOutput


class TestPromptLoader:
    def test_loads_matching_v1(self):
        prompt = load_prompt("matching_v1")
        assert prompt.version == "matching_v1"

    def test_system_prompt_has_role_and_output_format(self):
        system = load_prompt("matching_v1").system_prompt
        assert "technical recruiter" in system
        assert "must-have" in system
        # Khối JSON quy định output phải nằm trong system prompt.
        assert '"matched_requirements"' in system
        assert "strong_match" in system

    def test_system_prompt_excludes_implementation_notes(self):
        """Phần ghi chú cho lập trình viên và test case KHÔNG được gửi cho model."""
        system = load_prompt("matching_v1").system_prompt
        assert "matching_agent.py" not in system
        assert "json.loads()" not in system
        assert "Test case tham khảo" not in system
        assert "agent_runs" not in system

    def test_user_template_keeps_its_own_markdown_headings(self):
        """Heading nằm trong code fence của template không được coi là ranh giới section."""
        template = load_prompt("matching_v1").user_template
        assert "## Resume / CV của ứng viên" in template
        assert "## Mô tả công việc (Job Description)" in template
        assert "## Yêu cầu" in template
        assert "{resume_text}" in template
        assert "{job_description_text}" in template

    def test_render_replaces_both_placeholders(self):
        rendered = load_prompt("matching_v1").render_user_prompt(
            resume_text="RESUME_HERE", job_description_text="JD_HERE"
        )
        assert "RESUME_HERE" in rendered and "JD_HERE" in rendered
        assert "{resume_text}" not in rendered and "{job_description_text}" not in rendered

    def test_render_survives_braces_in_input(self):
        """CV chứa code có dấu ngoặc nhọn không được làm vỡ việc render prompt."""
        resume = 'def f(): return {"a": 1, "b": {"c": 2}}'
        rendered = load_prompt("matching_v1").render_user_prompt(
            resume_text=resume, job_description_text="JD {0} {x}"
        )
        assert resume in rendered
        assert "JD {0} {x}" in rendered

    def test_missing_file_raises(self):
        with pytest.raises(PromptFileError):
            load_prompt("matching_v99_khong_ton_tai")


class TestGenericRenderUserPrompt:
    """`render_user_prompt` phải generic (`**kwargs`), không hardcode đúng 2 tham số — bug đã
    verify: gọi với placeholder thứ 3 (vd. `match_context` cho cover letter) trên chữ ký cũ
    không hề báo lỗi, chỉ âm thầm giữ nguyên `{match_context}` trong prompt gửi cho model."""

    def test_render_replaces_three_placeholders(self):
        rendered = load_prompt("cover_letter_v1").render_user_prompt(
            resume_text="RESUME_HERE",
            job_description_text="JD_HERE",
            match_context="MATCH_CONTEXT_HERE",
        )
        assert "RESUME_HERE" in rendered
        assert "JD_HERE" in rendered
        assert "MATCH_CONTEXT_HERE" in rendered
        assert "{resume_text}" not in rendered
        assert "{job_description_text}" not in rendered
        assert "{match_context}" not in rendered

    def test_two_param_call_still_works_on_two_placeholder_template(self):
        """Tương thích ngược: cách gọi cũ của matching_agent (đúng 2 tham số) vẫn hoạt động y
        hệt sau khi đổi sang `**kwargs`."""
        rendered = load_prompt("matching_v1").render_user_prompt(
            resume_text="RESUME_HERE", job_description_text="JD_HERE"
        )
        assert "RESUME_HERE" in rendered and "JD_HERE" in rendered
        assert "{resume_text}" not in rendered and "{job_description_text}" not in rendered

    def test_extra_kwarg_with_no_matching_placeholder_is_a_no_op(self):
        rendered = load_prompt("matching_v1").render_user_prompt(
            resume_text="R", job_description_text="J", unused_key="SHOULD_NOT_APPEAR"
        )
        assert "SHOULD_NOT_APPEAR" not in rendered


class TestParseAgentJson:
    VALID = '{"score": 80, "verdict": "good_match", "reasoning": "ok", ' \
            '"matched_requirements": [], "missing_requirements": [], "suggestions": []}'

    def test_plain_json(self):
        assert parse_agent_json(self.VALID)["score"] == 80

    def test_json_code_fence(self):
        assert parse_agent_json(f"```json\n{self.VALID}\n```")["score"] == 80

    def test_bare_code_fence(self):
        assert parse_agent_json(f"```\n{self.VALID}\n```")["score"] == 80

    def test_preamble_and_postamble(self):
        raw = f"Đây là đánh giá của tôi:\n{self.VALID}\nHy vọng hữu ích!"
        assert parse_agent_json(raw)["score"] == 80

    def test_empty_response_raises(self):
        with pytest.raises(ValueError):
            parse_agent_json("   ")

    def test_prose_only_raises(self):
        with pytest.raises(ValueError):
            parse_agent_json("Tôi không thể đánh giá job này.")

    def test_json_array_raises(self):
        """JSON hợp lệ nhưng không phải object thì vẫn phải từ chối."""
        with pytest.raises(ValueError):
            parse_agent_json("[1, 2, 3]")


class TestMatchOutput:
    BASE = {
        "score": 70,
        "verdict": "good_match",
        "reasoning": "Có nền tảng React tốt.",
        "matched_requirements": ["React"],
        "missing_requirements": [],
        "suggestions": [],
    }

    def test_valid(self):
        assert MatchOutput.model_validate(self.BASE).score == 70

    @pytest.mark.parametrize("score", [-1, 101, 1000])
    def test_score_out_of_range(self, score):
        with pytest.raises(Exception):
            MatchOutput.model_validate({**self.BASE, "score": score})

    def test_unknown_verdict(self):
        with pytest.raises(Exception):
            MatchOutput.model_validate({**self.BASE, "verdict": "amazing_match"})

    def test_extra_field_rejected(self):
        with pytest.raises(Exception):
            MatchOutput.model_validate({**self.BASE, "salary_estimate": "2000 USD"})

    def test_missing_field_rejected(self):
        payload = {k: v for k, v in self.BASE.items() if k != "reasoning"}
        with pytest.raises(Exception):
            MatchOutput.model_validate(payload)

    def test_blank_items_are_dropped(self):
        out = MatchOutput.model_validate(
            {**self.BASE, "suggestions": ["Thêm số liệu", "", "   ", None]}
        )
        assert out.suggestions == ["Thêm số liệu"]

    def test_blank_reasoning_rejected(self):
        with pytest.raises(Exception):
            MatchOutput.model_validate({**self.BASE, "reasoning": "   "})
