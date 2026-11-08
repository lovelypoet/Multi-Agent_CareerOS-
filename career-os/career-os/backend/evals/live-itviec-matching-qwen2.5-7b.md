# Matching agent evaluation

- Run date (UTC): 2026-11-07 17:35:40
- Provider: `ollama`
- Model(s): `qwen2.5:7b`
- Prompt version(s): `matching_v1_ollama`
- Cases: 12

## Results

- Exact verdict accuracy: **9/12 (75.0%)**
- Macro F1 across the four verdicts: **0.742**
- Outcomes: 9 correct, 3 incorrect, 0 needs review, 0 errors
- Agent calls: 12; summed model latency: 78.0s; tokens: 30,091 input / 3,486 output

| Verdict | Support | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| `strong_match` | 3 | 1.000 | 1.000 | 1.000 |
| `good_match` | 3 | 1.000 | 0.667 | 0.800 |
| `partial_match` | 3 | 0.500 | 1.000 | 0.667 |
| `weak_match` | 3 | 1.000 | 0.333 | 0.500 |

## Cases to review

| Case | Expected | Result | Notes |
|---|---|---|---|
| `job_1_good_match` | `good_match` | predicted `partial_match` | Designed good profile: substantial relevant experience and most listing skills, with one stated gap. |
| `job_1_weak_match` | `weak_match` | predicted `partial_match` | Designed weak profile: no relevant software or AI experience. |
| `job_2_weak_match` | `weak_match` | predicted `partial_match` | Designed weak profile: no relevant software or AI experience. |

## Interpretation

This exploratory benchmark uses current live ITviec descriptions with controlled synthetic profiles. Its labels were assigned from the profile construction, not independently adjudicated by hiring experts. The score measures performance on these scenarios only and is not a real-world applicant-matching accuracy estimate.

## Live source postings

Job descriptions were fetched from ITviec at run time, used in memory, and not copied into this report.

| Company | Listing | URL |
|---|---|---|
| MB Bank | Senior AI Expert (Machine Learning, Deep Learning, LLM) | https://itviec.com/it-jobs/senior-ai-expert-machine-learning-deep-learning-llm-mb-bank-4932 |
| Trí Nghĩa Technology | Middle AI Engineer (LLM, RAG, ML, Python, PyTorch) | https://itviec.com/it-jobs/middle-ai-engineer-llm-rag-ml-python-pytorch-tri-nghia-technology-4531 |
| VinSOC | Senior/Expert AI Engineer (ML, LLM, Agentic AI, RAG) | https://itviec.com/it-jobs/senior-expert-ai-engineer-ml-llm-agentic-ai-rag-vinsoc-5952 |

## Benchmark limitations

This is an exploratory controlled benchmark, not independently adjudicated ground truth. The synthetic profile labels are assigned by construction (full skill coverage, one advertised-skill gap, limited overlap, or unrelated experience). Listing tags may not map exactly to must-have versus preferred requirements in the full posting. Use this to inspect behavior on current real postings, not as a CV accuracy claim.
