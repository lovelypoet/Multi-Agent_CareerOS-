"""Evaluate dense and hybrid resume retrieval against hand-labeled evidence queries."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.integrations.embedding_client import EmbeddingCallError, embed_text
from app.services.resume_retrieval import retrieve_resume_chunks

DEFAULT_DATASET = Path(__file__).resolve().parents[2] / "evals" / "resume-retrieval.json"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "evals" / "resume-retrieval-evaluation.md"
EmbedFunction = Callable[[str], Awaitable[list[float]]]


class RetrievalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    resume_text: str
    query: str
    expected_evidence: list[str] = Field(min_length=1)


def load_retrieval_cases(path: Path) -> list[RetrievalCase]:
    data: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("Retrieval evaluation dataset must be a non-empty JSON array.")
    cases = [RetrievalCase.model_validate(item) for item in data]
    ids = [case.case_id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Retrieval evaluation case_id values must be unique.")
    return cases


def _contains_evidence(chunk: str, expected_evidence: list[str]) -> bool:
    normalized_chunk = " ".join(chunk.casefold().split())
    return any(
        " ".join(evidence.casefold().split()) in normalized_chunk
        for evidence in expected_evidence
    )


async def evaluate_retrieval(
    cases: list[RetrievalCase],
    *,
    top_k: int = 3,
    minimum_similarity: float = 0.25,
    embed: EmbedFunction | None = None,
) -> list[dict[str, Any]]:
    if top_k < 1:
        raise ValueError("top_k must be at least 1.")
    embed_fn = embed or embed_text
    vector_cache: dict[str, list[float]] = {}

    async def cached_embed(text: str) -> list[float]:
        if text not in vector_cache:
            vector_cache[text] = await embed_fn(text)
        return vector_cache[text]

    outcomes = []
    for case in cases:
        ranked_by_strategy = {}
        for strategy in ("dense", "hybrid"):
            ranked_by_strategy[strategy] = await retrieve_resume_chunks(
                case.resume_text,
                [case.query],
                top_k_per_query=top_k,
                max_chunks=top_k,
                minimum_similarity=minimum_similarity,
                strategy=strategy,
                embed=cached_embed,
            )
        outcomes.append(
            {
                "case_id": case.case_id,
                "expected_evidence": case.expected_evidence,
                "dense": [
                    {
                        "text": item.text,
                        "hit": _contains_evidence(item.text, case.expected_evidence),
                        "similarity": item.similarity,
                    }
                    for item in ranked_by_strategy["dense"]
                ],
                "hybrid": [
                    {
                        "text": item.text,
                        "hit": _contains_evidence(item.text, case.expected_evidence),
                        "similarity": item.similarity,
                        "lexical_score": item.lexical_score,
                        "rerank_score": item.rerank_score,
                    }
                    for item in ranked_by_strategy["hybrid"]
                ],
            }
        )
    return outcomes


def _metrics(outcomes: list[dict[str, Any]], strategy: str, top_k: int) -> dict[str, float]:
    recall_at_1 = recall_at_k = precision_at_k = reciprocal_rank = 0.0
    for outcome in outcomes:
        ranked = outcome[strategy]
        hits = [index for index, item in enumerate(ranked) if item["hit"]]
        recall_at_1 += float(bool(hits) and hits[0] == 0)
        recall_at_k += float(bool(hits))
        precision_at_k += len(hits) / top_k
        reciprocal_rank += 1 / (hits[0] + 1) if hits else 0.0
    denominator = len(outcomes) or 1
    return {
        "recall_at_1": recall_at_1 / denominator,
        "recall_at_k": recall_at_k / denominator,
        "precision_at_k": precision_at_k / denominator,
        "mrr": reciprocal_rank / denominator,
    }


def render_retrieval_report(
    outcomes: list[dict[str, Any]],
    *,
    model: str,
    top_k: int,
    minimum_similarity: float,
) -> str:
    dense = _metrics(outcomes, "dense", top_k)
    hybrid = _metrics(outcomes, "hybrid", top_k)
    lines = [
        "# Resume retrieval evaluation",
        "",
        f"- Run date (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Embedding model: `{model}`",
        f"- Hand-labeled queries: {len(outcomes)}",
        f"- Ranking: top {top_k}; minimum cosine similarity {minimum_similarity:.2f}",
        "",
        "| Metric | Dense-only | BM25 + vector + explainable rerank |",
        "|---|---:|---:|",
        f"| Recall@1 | {dense['recall_at_1']:.1%} | {hybrid['recall_at_1']:.1%} |",
        f"| Recall@{top_k} | {dense['recall_at_k']:.1%} | {hybrid['recall_at_k']:.1%} |",
        f"| Precision@{top_k} | {dense['precision_at_k']:.3f} | {hybrid['precision_at_k']:.3f} |",
        f"| MRR@{top_k} | {dense['mrr']:.3f} | {hybrid['mrr']:.3f} |",
        "",
        "| Case | Expected evidence | Dense rank 1 | Hybrid rank 1 |",
        "|---|---|---|---|",
    ]
    for outcome in outcomes:
        dense_first = outcome["dense"][0]["text"] if outcome["dense"] else "(none)"
        hybrid_first = outcome["hybrid"][0]["text"] if outcome["hybrid"] else "(none)"
        expected = " / ".join(outcome["expected_evidence"]).replace("|", "\\|")
        dense_first = dense_first.replace("|", "\\|")
        hybrid_first = hybrid_first.replace("|", "\\|")
        lines.append(
            f"| `{outcome['case_id']}` | {expected} | {dense_first} | {hybrid_first} |"
        )
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "The query dataset is synthetic and hand-labeled. It is an initial retrieval "
            "regression set, not a representative estimate of retrieval quality on the user's "
            "resume or real hiring data. Similarity and lexical overlap do not establish that "
            "a candidate meets a job requirement. Expand this dataset with reviewed, real-profile "
            "evidence before tuning weights or claiming an improvement.",
            "",
        ]
    )
    return "\n".join(lines)


async def _run(dataset: Path, output: Path, *, top_k: int, minimum_similarity: float) -> None:
    cases = load_retrieval_cases(dataset)
    outcomes = await evaluate_retrieval(
        cases,
        top_k=top_k,
        minimum_similarity=minimum_similarity,
    )
    from app.core.config import get_settings

    report = render_retrieval_report(
        outcomes,
        model=get_settings().embedding_model,
        top_k=top_k,
        minimum_similarity=minimum_similarity,
    )
    output.write_text(report, encoding="utf-8")
    print(report)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--minimum-similarity", type=float, default=0.25)
    args = parser.parse_args()
    if args.top_k < 1:
        parser.error("--top-k must be positive.")
    if not 0 <= args.minimum_similarity <= 1:
        parser.error("--minimum-similarity must be between 0 and 1.")
    try:
        asyncio.run(
            _run(
                args.dataset,
                args.output,
                top_k=args.top_k,
                minimum_similarity=args.minimum_similarity,
            )
        )
    except EmbeddingCallError as exc:
        parser.exit(1, f"Embedding retrieval failed: {exc}\n")


if __name__ == "__main__":
    main()
