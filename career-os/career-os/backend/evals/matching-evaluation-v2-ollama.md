# Matching agent evaluation

- Run date (UTC): 2026-11-08 16:02:20
- Provider: `ollama`
- Model(s): `qwen2.5:7b`
- Prompt version(s): `matching_v2_ollama`
- Cases: 24

## Results

- Exact verdict accuracy: **16/24 (66.7%)**
- Macro F1 across the four verdicts: **0.659**
- Outcomes: 16 correct, 8 incorrect, 0 needs review, 0 errors
- Agent calls: 24; summed model latency: 283.7s; tokens: 24,828 input / 13,658 output
- Structured JD analysis: 24/24 cases; CV evidence quotes: 74/132 assessed requirements

| Verdict | Support | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| `strong_match` | 6 | 1.000 | 0.833 | 0.909 |
| `good_match` | 6 | 1.000 | 0.333 | 0.500 |
| `partial_match` | 6 | 0.375 | 0.500 | 0.429 |
| `weak_match` | 6 | 0.667 | 1.000 | 0.800 |

## Cases to review

| Case | Expected | Result | Score | Structured requirements | Notes |
|---|---|---|---:|---:|---|
| `good_react_missing_typescript` | `good_match` | predicted `partial_match` | 62 | 5 | Matches the React and experience requirements but lacks one important required skill, TypeScript. |
| `good_data_engineer_missing_snowflake` | `good_match` | predicted `partial_match` | 62 | 7 | Meets the core pipeline requirements and experience level but has a gap in the specified data warehouse. |
| `good_qa_missing_java` | `good_match` | predicted `partial_match` | 56 | 5 | Strongly matches automation, Selenium, and API testing requirements, but misses the required Java skill. |
| `partial_support_to_backend` | `partial_match` | predicted `weak_match` | 20 | 5 | Linux and SQL experience are relevant, but the core professional backend and Python requirements are missing. |
| `partial_analyst_missing_python` | `partial_match` | predicted `weak_match` | 19 | 5 | Matches the experience, SQL, dashboarding, and communication requirements but lacks required Python analysis skills. |
| `strong_security_engineer` | `strong_match` | predicted `partial_match` | 50 | 1 | Direct evidence covers every required security area and both preferred certifications. |
| `good_ml_missing_pytorch` | `good_match` | predicted `partial_match` | 56 | 5 | Matches all required experience and one preferred deployment tool, but PyTorch is absent. |
| `partial_data_analyst_missing_python` | `partial_match` | predicted `weak_match` | 33 | 6 | Has analytics, SQL, and Tableau evidence but lacks two required analysis skills. |

## Interpretation

This 24-case balanced benchmark uses hand-authored synthetic resume/JD pairs. Labels are scenario-based annotations, not independently adjudicated hiring decisions or proof of production accuracy. Review case-level results and source-quote coverage; exact-verdict accuracy counts errors and review-required outcomes as incorrect.
