# Matching agent evaluation

- Run date (UTC): 2026-11-07 17:20:11
- Provider: `ollama_ensemble`
- Model(s): `llama3.1:8b`, `qwen2.5:7b`
- Prompt version(s): `matching_v1`
- Cases: 12

## Results

- Exact verdict accuracy: **7/12 (58.3%)**
- Macro F1 across the four verdicts: **0.664**
- Outcomes: 7 correct, 1 incorrect, 4 needs review, 0 errors
- Agent calls: 24; summed model latency: 343.5s; tokens: 19,278 input / 3,939 output

| Verdict | Support | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| `strong_match` | 3 | 1.000 | 0.667 | 0.800 |
| `good_match` | 3 | 0.750 | 1.000 | 0.857 |
| `partial_match` | 3 | 1.000 | 0.333 | 0.500 |
| `weak_match` | 3 | 1.000 | 0.333 | 0.500 |

## Cases to review

| Case | Expected | Result | Notes |
|---|---|---|---|
| `strong_platform_engineer` | `strong_match` | needs review (no verdict) | Provides substantial experience with every required technology and both preferred areas. |
| `partial_support_to_backend` | `partial_match` | predicted `good_match` | Linux and SQL experience are relevant, but the core professional backend and Python requirements are missing. |
| `partial_analyst_missing_python` | `partial_match` | needs review (no verdict) | Matches the experience, SQL, dashboarding, and communication requirements but lacks required Python analysis skills. |
| `weak_hospitality_to_distributed_java` | `weak_match` | needs review (no verdict) | The resume provides no evidence of the required professional software, Java, or distributed-systems experience. |
| `weak_admin_to_ml_engineer` | `weak_match` | needs review (no verdict) | There is no evidence for the required software engineering or machine-learning experience. |

## Interpretation

This is an initial, small, hand-labeled benchmark of verdict classification, not proof of production accuracy. The labels reflect the rubric in `prompts/matching_v1.md`; review the case-level results and dataset, and expand it before making broad quality claims. Exact-verdict accuracy counts errors and review-required outcomes as incorrect.
