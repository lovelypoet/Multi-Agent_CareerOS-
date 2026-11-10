import pytest

from app.schemas.match import MatchOutput
from app.services.match_evidence import verify_and_score_match


def _output() -> MatchOutput:
    return MatchOutput.model_validate(
        {
            "score": 99,
            "verdict": "strong_match",
            "reasoning": "React is a match.",
            "matched_requirements": [],
            "missing_requirements": [],
            "suggestions": [],
            "jd_analysis": {
                "role_title": "Frontend Developer",
                "experience_level": None,
                "tech_stack": ["React", "TypeScript", "AWS"],
                "requirements": [
                    {
                        "text": "React experience",
                        "priority": "required",
                        "category": "skill",
                        "jd_quote": "React is required.",
                    },
                    {
                        "text": "TypeScript experience",
                        "priority": "required",
                        "category": "skill",
                        "jd_quote": "TypeScript is required.",
                    },
                    {
                        "text": "AWS experience",
                        "priority": "preferred",
                        "category": "skill",
                        "jd_quote": "AWS is a plus.",
                    },
                    {
                        "text": "Invented requirement",
                        "priority": "required",
                        "category": "other",
                        "jd_quote": "Must have Kubernetes certification.",
                    },
                ],
            },
            "requirement_assessments": [
                {"requirement_index": 0, "status": "met", "cv_evidence": "I use React daily."},
                {
                    "requirement_index": 1,
                    "status": "met",
                    "cv_evidence": "I have five years of TypeScript.",
                },
                {"requirement_index": 2, "status": "partial", "cv_evidence": "I used AWS once."},
                {
                    "requirement_index": 3,
                    "status": "met",
                    "cv_evidence": "Kubernetes certification",
                },
            ],
        }
    )


def test_score_is_recomputed_from_verified_weighted_requirements():
    result = verify_and_score_match(
        _output(),
        resume_text="I use React daily. I have five years of TypeScript. I used AWS once.",
        job_description_text="React is required. TypeScript is required. AWS is a plus.",
    )

    assert result.score == 90
    assert result.verdict == "strong_match"
    assert result.matched_requirements == ["React", "TypeScript"]
    assert result.missing_requirements == ["AWS"]
    assert len(result.jd_analysis.requirements) == 3
    assert [item.requirement_index for item in result.requirement_assessments] == [0, 1, 2]
    assert result.requirement_assessments[2].status == "partial"
    assert result.requirement_assessments[2].cv_evidence == "I used AWS once."


def test_jd_quote_must_be_found_and_missing_cv_evidence_is_not_a_match():
    result = verify_and_score_match(
        _output(),
        resume_text="I use React daily.",
        job_description_text="React is required. TypeScript is required. AWS is a plus.",
    )

    assert all("Invented" not in requirement.text for requirement in result.jd_analysis.requirements)
    assert result.score == 40
    assert result.verdict == "partial_match"
    assert result.matched_requirements == ["React"]
    assert result.missing_requirements == ["TypeScript", "AWS"]


def test_unrelated_quote_is_replaced_with_a_source_sentence_about_the_requirement():
    output = _output()
    output.requirement_assessments[0].cv_evidence = "I have five years of TypeScript."

    result = verify_and_score_match(
        output,
        resume_text="I use React daily. I have five years of TypeScript.",
        job_description_text="React is required. TypeScript is required. AWS is a plus.",
    )

    assert result.requirement_assessments[0].status == "met"
    assert result.requirement_assessments[0].cv_evidence == "I use React daily."


def test_grouped_model_requirements_are_split_and_assessed_independently():
    output = MatchOutput.model_validate(
        {
            "score": 99,
            "verdict": "strong_match",
            "reasoning": "Close match.",
            "jd_analysis": {
                "role_title": "Backend Engineer",
                "experience_level": None,
                "tech_stack": ["Python", "FastAPI", "PostgreSQL", "AWS"],
                "requirements": [
                    {
                        "text": "4+ years of backend experience, Python, FastAPI, PostgreSQL, AWS",
                        "priority": "required",
                        "category": "experience",
                        "jd_quote": "Required: 4+ years backend experience, Python, FastAPI, PostgreSQL, AWS.",
                    }
                ],
            },
            "requirement_assessments": [
                {"requirement_index": 0, "status": "missing", "cv_evidence": ""}
            ],
        }
    )
    resume = (
        "Backend engineer with 6 years of experience. "
        "Built Python and FastAPI services with PostgreSQL. "
        "No AWS experience."
    )

    result = verify_and_score_match(
        output,
        resume_text=resume,
        job_description_text="Required: 4+ years backend experience, Python, FastAPI, PostgreSQL, AWS.",
    )

    assert [requirement.text for requirement in result.jd_analysis.requirements] == [
        "4+ years of backend experience",
        "Python",
        "FastAPI",
        "PostgreSQL",
        "AWS",
    ]
    assert [item.status for item in result.requirement_assessments] == [
        "met",
        "met",
        "met",
        "met",
        "missing",
    ]
    assert result.score == 80


def test_known_technology_omitted_from_model_tech_stack_is_still_split_from_jd_quote():
    output = MatchOutput.model_validate(
        {
            "score": 0,
            "verdict": "weak_match",
            "reasoning": "No match.",
            "jd_analysis": {
                "role_title": "Frontend Developer",
                "experience_level": None,
                "tech_stack": ["TypeScript"],
                "requirements": [
                    {
                        "text": "3+ years of React and production experience with TypeScript",
                        "priority": "required",
                        "category": "experience",
                        "jd_quote": "Must have 3+ years of React and production experience with TypeScript.",
                    }
                ],
            },
            "requirement_assessments": [
                {"requirement_index": 0, "status": "missing", "cv_evidence": ""}
            ],
        }
    )
    result = verify_and_score_match(
        output,
        resume_text=(
            "Frontend developer with 3 years of professional experience building React applications. "
            "No TypeScript experience is listed."
        ),
        job_description_text=(
            "Must have 3+ years of React and production experience with TypeScript."
        ),
    )

    assert [requirement.text for requirement in result.jd_analysis.requirements] == [
        "3+ years React",
        "React",
        "TypeScript",
    ]
    assert [item.status for item in result.requirement_assessments] == ["met", "met", "missing"]


def test_explicit_negative_statement_cannot_be_used_as_positive_evidence():
    output = _output()
    output.requirement_assessments[0].status = "met"
    output.requirement_assessments[0].cv_evidence = "No React experience is listed."

    result = verify_and_score_match(
        output,
        resume_text="No React experience is listed.",
        job_description_text="React is required. TypeScript is required. AWS is a plus.",
    )

    assert result.requirement_assessments[0].status == "missing"
    assert result.requirement_assessments[0].cv_evidence == ""


def test_structured_analysis_without_verifiable_jd_quotes_is_rejected():
    output = _output()
    output.jd_analysis.requirements = [output.jd_analysis.requirements[-1]]
    with pytest.raises(ValueError, match="no requirement quote"):
        verify_and_score_match(
            output,
            resume_text="Kubernetes certification",
            job_description_text="Only React is required.",
        )


def test_legacy_output_is_explicitly_not_evidence_based():
    output = MatchOutput.model_validate(
        {
            "score": 72,
            "verdict": "good_match",
            "reasoning": "Legacy analysis.",
        }
    )
    result = verify_and_score_match(output, resume_text="CV", job_description_text="JD")

    assert result.score == 72
    assert result.jd_analysis is None
    assert result.requirement_assessments == []
