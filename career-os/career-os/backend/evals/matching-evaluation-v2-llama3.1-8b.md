# Matching agent evaluation

- Run date (UTC): 2026-11-08 17:09:34
- Provider: `ollama`
- Model(s): `llama3.1:8b`
- Prompt version(s): `matching_v2_ollama`
- Cases: 24

## Results

- Exact verdict accuracy: **13/24 (54.2%)**
- Macro F1 across the four verdicts: **0.527**
- Outcomes: 13 correct, 11 incorrect, 0 needs review, 0 errors
- Agent calls: 24; summed model latency: 270.9s; tokens: 24,394 input / 12,023 output
- Structured JD analysis: 24/24 cases; CV evidence quotes: 65/105 assessed requirements

| Verdict | Support | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| `strong_match` | 6 | 0.750 | 0.500 | 0.600 |
| `good_match` | 6 | 0.500 | 0.333 | 0.400 |
| `partial_match` | 6 | 0.286 | 0.333 | 0.308 |
| `weak_match` | 6 | 0.667 | 1.000 | 0.800 |

## Cases to review

| Case | Expected | Result | Score | Structured requirements | Notes |
|---|---|---|---:|---:|---|
| `strong_platform_engineer` | `strong_match` | predicted `good_match` | 83 | 2 | Provides substantial experience with every required technology and both preferred areas. |
| `good_react_missing_typescript` | `good_match` | predicted `partial_match` | 45 | 6 | Matches the React and experience requirements but lacks one important required skill, TypeScript. |
| `good_data_engineer_missing_snowflake` | `good_match` | predicted `partial_match` | 55 | 6 | Meets the core pipeline requirements and experience level but has a gap in the specified data warehouse. |
| `partial_python_junior` | `partial_match` | predicted `good_match` | 75 | 2 | Has a relevant Python and Django foundation but falls well short of the experience and operational requirements. |
| `partial_support_to_backend` | `partial_match` | predicted `weak_match` | 33 | 5 | Linux and SQL experience are relevant, but the core professional backend and Python requirements are missing. |
| `partial_analyst_missing_python` | `partial_match` | predicted `weak_match` | 14 | 4 | Matches the experience, SQL, dashboarding, and communication requirements but lacks required Python analysis skills. |
| `strong_security_engineer` | `strong_match` | predicted `partial_match` | 56 | 5 | Direct evidence covers every required security area and both preferred certifications. |
| `strong_data_engineer` | `strong_match` | predicted `partial_match` | 50 | 2 | Meets all five core requirements and documents both preferred tools. |
| `good_frontend_missing_accessibility` | `good_match` | predicted `strong_match` | 85 | 7 | All core requirements are evidenced; one of two preferred areas is not documented. |
| `good_ml_missing_pytorch` | `good_match` | predicted `partial_match` | 60 | 6 | Matches all required experience and one preferred deployment tool, but PyTorch is absent. |
| `partial_data_analyst_missing_python` | `partial_match` | predicted `weak_match` | 28 | 5 | Has analytics, SQL, and Tableau evidence but lacks two required analysis skills. |

## Interpretation

This 24-case balanced benchmark uses hand-authored synthetic resume/JD pairs. Labels are scenario-based annotations, not independently adjudicated hiring decisions or proof of production accuracy. Review case-level results and source-quote coverage; exact-verdict accuracy counts errors and review-required outcomes as incorrect.
