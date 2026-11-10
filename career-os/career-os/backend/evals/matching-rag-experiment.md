# Experimental RAG matching evaluation

- Run date (UTC): 2026-11-08 17:35:51
- Provider/model: `ollama` / `qwen2.5:7b`
- Cases: 24
- Retrieval: top 1 chunks per requirement, at most 12 chunks, minimum cosine similarity 0.25

## Baseline vs RAG

| Metric | Full CV baseline | Retrieved-context RAG |
|---|---:|---:|
| Exact verdict accuracy | 17/24 (70.8%) | 17/24 (70.8%) |
| Macro-F1 | 0.702 | 0.707 |
| CV evidence quotes | 73/129 | 72/127 |
| Cases with agent output | 24/24 | 24/24 |
| Agent calls made | 24 baseline | 24 RAG generation (plus baseline analysis to form retrieval queries) |

- Retrieved chunks per case: 2.1 of 2.7 resume chunks on average.
- Mean selected-chunk cosine similarity: 0.535

| Case | Expected | Baseline | RAG | Chunks |
|---|---|---|---|---:|
| `strong_backend_python` | `strong_match` | `strong_match` | `strong_match` | 2 |
| `strong_frontend_react` | `strong_match` | `strong_match` | `strong_match` | 1 |
| `strong_platform_engineer` | `strong_match` | `strong_match` | `strong_match` | 2 |
| `good_react_missing_typescript` | `good_match` | `partial_match` | `partial_match` | 4 |
| `good_data_engineer_missing_snowflake` | `good_match` | `partial_match` | `partial_match` | 2 |
| `good_qa_missing_java` | `good_match` | `good_match` | `good_match` | 2 |
| `partial_python_junior` | `partial_match` | `partial_match` | `partial_match` | 3 |
| `partial_support_to_backend` | `partial_match` | `weak_match` | `weak_match` | 2 |
| `partial_analyst_missing_python` | `partial_match` | `weak_match` | `weak_match` | 3 |
| `weak_hospitality_to_distributed_java` | `weak_match` | `weak_match` | `weak_match` | 2 |
| `weak_design_to_sre` | `weak_match` | `weak_match` | `weak_match` | 1 |
| `weak_admin_to_ml_engineer` | `weak_match` | `weak_match` | `weak_match` | 1 |
| `strong_security_engineer` | `strong_match` | `good_match` | `partial_match` | 3 |
| `strong_data_engineer` | `strong_match` | `strong_match` | `strong_match` | 2 |
| `strong_qa_automation` | `strong_match` | `strong_match` | `strong_match` | 2 |
| `good_backend_missing_redis` | `good_match` | `good_match` | `good_match` | 3 |
| `good_frontend_missing_accessibility` | `good_match` | `good_match` | `good_match` | 2 |
| `good_ml_missing_pytorch` | `good_match` | `partial_match` | `partial_match` | 2 |
| `partial_data_analyst_missing_python` | `partial_match` | `weak_match` | `good_match` | 2 |
| `partial_devops_missing_kubernetes` | `partial_match` | `partial_match` | `partial_match` | 3 |
| `partial_product_analyst` | `partial_match` | `partial_match` | `partial_match` | 2 |
| `weak_mobile_to_backend` | `weak_match` | `weak_match` | `weak_match` | 2 |
| `weak_marketing_to_data_science` | `weak_match` | `weak_match` | `weak_match` | 1 |
| `weak_support_to_security` | `weak_match` | `weak_match` | `weak_match` | 1 |

## Real-profile smoke test (not an accuracy evaluation)

- Used the locally saved active resume and the stored `ML Engineer - Computer Vision/Edge AI (Fresher-Junior)` job description; the specific Apero JD was not present locally.
- Full-resume baseline: `weak_match`, score 0, CV evidence on 0/8 requirements.
- Retrieved-context run: `weak_match`, score 0, CV evidence on 0/13 requirements; retrieved 5 of 82 resume chunks with mean cosine similarity 0.302.
- This confirms the retrieval-and-generation path runs on the saved profile, but does not show a benefit on this JD. Zero verified evidence is not proof the candidate has no relevant experience; it means neither run produced evidence that passed the current verifier.

## Limitations

This is an experimental two-pass flow: the full-CV agent run supplies requirement queries, then the same agent runs again on retrieved CV chunks. Baseline uses one generation call; RAG uses up to two, so this is not yet a latency- or cost-neutral production design. The 24 hand-authored synthetic resume/JD pairs are short and do not represent the user's full career history; retrieval quality and verdict labels must be validated on longer, independently reviewed profiles before enabling it in the application. The single real-profile smoke test has no independent ground-truth labels. Similarity is a retrieval signal, not evidence that a requirement is satisfied.
