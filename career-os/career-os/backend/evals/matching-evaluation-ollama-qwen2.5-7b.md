# Matching agent evaluation

- Run date (UTC): 2026-11-07 17:13:42
- Provider: `ollama`
- Model(s): `qwen2.5:7b`
- Prompt version(s): `matching_v1_ollama`
- Cases: 12

## Results

- Exact verdict accuracy: **6/12 (50.0%)**
- Macro F1 across the four verdicts: **0.417**
- Outcomes: 6 correct, 6 incorrect, 0 needs review, 0 errors
- Agent calls: 12; summed model latency: 54.0s; tokens: 20,704 input / 2,114 output

| Verdict | Support | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| `strong_match` | 3 | 0.000 | 0.000 | 0.000 |
| `good_match` | 3 | 0.000 | 0.000 | 0.000 |
| `partial_match` | 3 | 0.500 | 1.000 | 0.667 |
| `weak_match` | 3 | 1.000 | 1.000 | 1.000 |

## Cases to review

| Case | Expected | Result | Notes |
|---|---|---|---|
| `strong_backend_python` | `strong_match` | predicted `good_match` | Meets every stated must-have and both preferred skills with directly relevant production experience. |
| `strong_frontend_react` | `strong_match` | predicted `good_match` | Exceeds the experience requirement and documents all required and preferred technologies. |
| `strong_platform_engineer` | `strong_match` | predicted `good_match` | Provides substantial experience with every required technology and both preferred areas. |
| `good_react_missing_typescript` | `good_match` | predicted `partial_match` | Matches the React and experience requirements but lacks one important required skill, TypeScript. |
| `good_data_engineer_missing_snowflake` | `good_match` | predicted `partial_match` | Meets the core pipeline requirements and experience level but has a gap in the specified data warehouse. |
| `good_qa_missing_java` | `good_match` | predicted `partial_match` | Strongly matches automation, Selenium, and API testing requirements, but misses the required Java skill. |

## Interpretation

This is an initial, small, hand-labeled benchmark of verdict classification, not proof of production accuracy. The labels reflect the rubric in `prompts/matching_v1.md`; review the case-level results and dataset, and expand it before making broad quality claims. Exact-verdict accuracy counts errors and review-required outcomes as incorrect.
