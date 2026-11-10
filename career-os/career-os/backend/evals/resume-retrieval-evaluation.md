# Resume retrieval evaluation

- Run date (UTC): 2026-11-08 18:20:53
- Embedding model: `nomic-embed-text-v2-moe`
- Hand-labeled queries: 20
- Ranking: top 3; minimum cosine similarity 0.25

| Metric | Dense-only | BM25 + vector + explainable rerank |
|---|---:|---:|
| Recall@1 | 95.0% | 100.0% |
| Recall@3 | 100.0% | 100.0% |
| Precision@3 | 0.333 | 0.333 |
| MRR@3 | 0.975 | 1.000 |

| Case | Expected evidence | Dense rank 1 | Hybrid rank 1 |
|---|---|---|---|
| `backend-fastapi` | Built Python and FastAPI services for customer-facing APIs. | Built Python and FastAPI services for customer-facing APIs. | Built Python and FastAPI services for customer-facing APIs. |
| `cloud-negative` | No AWS deployment experience is listed. | No AWS deployment experience is listed. | No AWS deployment experience is listed. |
| `typescript-negative` | No TypeScript experience is listed. | No TypeScript experience is listed. | No TypeScript experience is listed. |
| `vietnamese-fastapi` | Xây dựng API bằng Python và FastAPI, lưu dữ liệu trên PostgreSQL. | Xây dựng API bằng Python và FastAPI, lưu dữ liệu trên PostgreSQL. | Xây dựng API bằng Python và FastAPI, lưu dữ liệu trên PostgreSQL. |
| `ml-evaluation` | Trained image classifiers with PyTorch and measured precision, recall, and F1 on held-out data. | Trained image classifiers with PyTorch and measured precision, recall, and F1 on held-out data. | Trained image classifiers with PyTorch and measured precision, recall, and F1 on held-out data. |
| `accessibility` | Improved keyboard navigation and screen-reader labels across React checkout flows. | Improved keyboard navigation and screen-reader labels across React checkout flows. | Improved keyboard navigation and screen-reader labels across React checkout flows. |
| `manufacturing-aoi` | Operated SMT and AOI inspection workflows at a Foxconn electronics production line. | Operated SMT and AOI inspection workflows at a Foxconn electronics production line. | Operated SMT and AOI inspection workflows at a Foxconn electronics production line. |
| `rag-project` | Implemented retrieval-augmented generation with vector search and source citations for internal support documents. | Implemented retrieval-augmented generation with vector search and source citations for internal support documents. | Implemented retrieval-augmented generation with vector search and source citations for internal support documents. |
| `sql-analytics` | Wrote SQL joins and window functions to analyze customer retention cohorts. | Wrote SQL joins and window functions to analyze customer retention cohorts. | Wrote SQL joins and window functions to analyze customer retention cohorts. |
| `airflow-pipelines` | Scheduled batch ETL workflows with Apache Airflow and added data quality checks. | Scheduled batch ETL workflows with Apache Airflow and added data quality checks. | Scheduled batch ETL workflows with Apache Airflow and added data quality checks. |
| `leadership-incident` | Led incident response for distributed production services and wrote postmortems that reduced repeat outages. | Led incident response for distributed production services and wrote postmortems that reduced repeat outages. | Led incident response for distributed production services and wrote postmortems that reduced repeat outages. |
| `research-award` | Received a university research award for a computer-vision project and presented the results at a student symposium. | Received a university research award for a computer-vision project and presented the results at a student symposium. | Received a university research award for a computer-vision project and presented the results at a student symposium. |
| `aws-vs-azure` | No AWS deployment experience is listed. | No AWS deployment experience is listed. | No AWS deployment experience is listed. |
| `react-vs-vue` | Prototyped React components in a weekend project and has not used TypeScript. | Prototyped React components in a weekend project and has not used TypeScript. | Prototyped React components in a weekend project and has not used TypeScript. |
| `pytorch-vs-tensorflow` | No PyTorch experience is listed. | No PyTorch experience is listed. | No PyTorch experience is listed. |
| `postgres-vs-mysql` | Has not used PostgreSQL. | Designed MySQL schemas and optimized production queries. | Has not used PostgreSQL. |
| `kubernetes-vs-docker` | No Kubernetes orchestration experience. | No Kubernetes orchestration experience. | No Kubernetes orchestration experience. |
| `airflow-vs-prefect` | Has not used Apache Airflow. | Has not used Apache Airflow. | Has not used Apache Airflow. |
| `research-award-vs-course` | Received a university research award for an original object-detection project. | Received a university research award for an original object-detection project. | Received a university research award for an original object-detection project. |
| `product-prototype` | Interviewed five users, built an LLM-powered prototype, and measured task completion before and after the change. | Interviewed five users, built an LLM-powered prototype, and measured task completion before and after the change. | Interviewed five users, built an LLM-powered prototype, and measured task completion before and after the change. |

## Limitations

The 12-query dataset is synthetic and hand-labeled. It is an initial retrieval regression set, not a representative estimate of retrieval quality on the user's resume or real hiring data. Similarity and lexical overlap do not establish that a candidate meets a job requirement. Expand this dataset with reviewed, real-profile evidence before tuning weights or claiming an improvement.
