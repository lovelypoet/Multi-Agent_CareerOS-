"""Compare full-resume matching with an experimental requirement-guided RAG flow."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Awaitable, Callable
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from app.core.agent_contract import AgentContext, AgentExecutionError, BaseAgent
from app.core.agent_registry import get_agent
from app.core.config import get_settings
from app.integrations.embedding_client import EmbeddingCallError
from app.scripts.evaluate_matching import (
    DEFAULT_DATASET,
    VERDICTS,
    EvaluationCase,
    _class_metrics,
    load_cases,
)
from app.services.resume_retrieval import retrieve_resume_chunks, split_resume_chunks

DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[2] / "evals" / "matching-rag-experiment.md"
)
EmbedFunction = Callable[[str], Awaitable[list[float]]]


async def _run_agent(agent: BaseAgent, resume: str, jd: str) -> dict:
    try:
        result = await agent.run(AgentContext(resume_text=resume, job_description_text=jd))
    except AgentExecutionError as exc:
        return {
            "actual": None,
            "status": "error",
            "error": str(exc)[:240],
            "output": None,
            "run_logs": exc.run_logs,
        }
    if result.needs_review or result.output is None:
        return {
            "actual": None,
            "status": "needs_review",
            "output": None,
            "run_logs": result.run_logs,
        }
    return {
        "actual": result.output["verdict"],
        "status": "success",
        "output": result.output,
        "run_logs": result.run_logs,
    }


async def evaluate_rag_cases(
    cases: list[EvaluationCase],
    agent: BaseAgent,
    *,
    top_k_per_query: int = 1,
    max_chunks: int = 12,
    minimum_similarity: float = 0.25,
    retrieval_strategy: str = "hybrid",
    embed: EmbedFunction | None = None,
) -> list[dict]:
    outcomes = []
    for case in cases:
        baseline = await _run_agent(agent, case.resume_text, case.job_description)
        baseline_output = baseline["output"]
        if baseline_output is None:
            queries = [case.job_description]
        else:
            analysis = baseline_output.get("jd_analysis") or {}
            queries = [
                requirement["text"]
                for requirement in analysis.get("requirements", [])
                if requirement.get("text")
            ] or [case.job_description]

        retrieved = await retrieve_resume_chunks(
            case.resume_text,
            queries,
            top_k_per_query=top_k_per_query,
            max_chunks=max_chunks,
            minimum_similarity=minimum_similarity,
            strategy=retrieval_strategy,
            embed=embed,
        )
        if retrieved:
            rag = await _run_agent(
                agent,
                "\n".join(chunk.text for chunk in retrieved),
                case.job_description,
            )
        else:
            rag = {
                "actual": None,
                "status": "no_retrieved_context",
                "output": None,
                "run_logs": [],
            }

        outcomes.append(
            {
                "case_id": case.case_id,
                "expected": case.expected_verdict,
                "rationale": case.rationale,
                "baseline": baseline,
                "rag": rag,
                "retrieved_chunks": len(retrieved),
                "resume_chunks": len(split_resume_chunks(case.resume_text)),
                "retrieval_similarity": (
                    sum(chunk.similarity for chunk in retrieved) / len(retrieved)
                    if retrieved
                    else None
                ),
                "retrieval_lexical_score": (
                    sum(chunk.lexical_score for chunk in retrieved) / len(retrieved)
                    if retrieved
                    else None
                ),
                "retrieval_rerank_score": (
                    sum(chunk.rerank_score for chunk in retrieved) / len(retrieved)
                    if retrieved
                    else None
                ),
            }
        )
    return outcomes


def _accuracy(outcomes: list[dict], method: str) -> tuple[int, float, float]:
    predicted = [outcome[method]["actual"] for outcome in outcomes]
    expected = [outcome["expected"] for outcome in outcomes]
    correct = sum(actual == guess for actual, guess in zip(expected, predicted))
    macro_f1 = sum(
        _class_metrics(expected, predicted, label)[2] for label in VERDICTS
    ) / len(VERDICTS)
    return correct, correct / len(outcomes) if outcomes else 0.0, macro_f1


def _evidence_totals(outcomes: list[dict], method: str) -> tuple[int, int]:
    total = evidenced = 0
    for outcome in outcomes:
        output = outcome[method]["output"]
        if output is None:
            continue
        analysis = output.get("jd_analysis") or {}
        assessments = output.get("requirement_assessments") or []
        total += len(analysis.get("requirements", []))
        evidenced += sum(
            assessment.get("status") in {"met", "partial"}
            and bool(assessment.get("cv_evidence"))
            for assessment in assessments
        )
    return evidenced, total


def render_rag_report(
    cases: list[EvaluationCase],
    outcomes: list[dict],
    *,
    provider: str,
    model: str,
    top_k_per_query: int,
    max_chunks: int,
    minimum_similarity: float,
    retrieval_strategy: str = "hybrid",
) -> str:
    if len(cases) != len(outcomes):
        raise ValueError("Each evaluation case must have exactly one outcome.")
    baseline_correct, baseline_accuracy, baseline_f1 = _accuracy(outcomes, "baseline")
    rag_correct, rag_accuracy, rag_f1 = _accuracy(outcomes, "rag")
    baseline_evidence, baseline_total = _evidence_totals(outcomes, "baseline")
    rag_evidence, rag_total = _evidence_totals(outcomes, "rag")
    baseline_statuses = Counter(outcome["baseline"]["status"] for outcome in outcomes)
    rag_statuses = Counter(outcome["rag"]["status"] for outcome in outcomes)
    avg_retrieved = (
        sum(outcome["retrieved_chunks"] for outcome in outcomes) / len(outcomes)
        if outcomes
        else 0
    )
    avg_resume_chunks = (
        sum(outcome["resume_chunks"] for outcome in outcomes) / len(outcomes)
        if outcomes
        else 0
    )
    rag_calls = sum(len(outcome["rag"]["run_logs"]) for outcome in outcomes)
    baseline_calls = sum(len(outcome["baseline"]["run_logs"]) for outcome in outcomes)
    avg_similarity = [
        outcome["retrieval_similarity"]
        for outcome in outcomes
        if outcome["retrieval_similarity"] is not None
    ]
    lines = [
        "# Experimental RAG matching evaluation",
        "",
        f"- Run date (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Provider/model: `{provider}` / `{model}`",
        f"- Cases: {len(cases)}",
        f"- Retrieval strategy: `{retrieval_strategy}`; top {top_k_per_query} chunks per "
        f"requirement, at most {max_chunks} chunks, minimum cosine similarity "
        f"{minimum_similarity:.2f}",
        "",
        "## Baseline vs RAG",
        "",
        "| Metric | Full CV baseline | Retrieved-context RAG |",
        "|---|---:|---:|",
        f"| Exact verdict accuracy | {baseline_correct}/{len(cases)} ({baseline_accuracy:.1%}) | "
        f"{rag_correct}/{len(cases)} ({rag_accuracy:.1%}) |",
        f"| Macro-F1 | {baseline_f1:.3f} | {rag_f1:.3f} |",
        f"| CV evidence quotes | {baseline_evidence}/{baseline_total} | "
        f"{rag_evidence}/{rag_total} |",
        f"| Cases with agent output | {baseline_statuses.get('success', 0)}/{len(cases)} | "
        f"{rag_statuses.get('success', 0)}/{len(cases)} |",
        f"| Agent calls made | {baseline_calls} baseline | {rag_calls} RAG generation "
        f"(plus baseline analysis to form retrieval queries) |",
        "",
        f"- Retrieved chunks per case: {avg_retrieved:.1f} of {avg_resume_chunks:.1f} resume chunks "
        f"on average.",
        (
            f"- Mean selected-chunk cosine similarity: "
            f"{sum(avg_similarity) / len(avg_similarity):.3f}"
            if avg_similarity
            else "- Mean selected-chunk cosine similarity: not available (no chunks retrieved)."
        ),
        "",
        "| Case | Expected | Baseline | RAG | Chunks |",
        "|---|---|---|---|---:|",
    ]
    for outcome in outcomes:
        baseline_actual = outcome["baseline"]["actual"] or outcome["baseline"]["status"]
        rag_actual = outcome["rag"]["actual"] or outcome["rag"]["status"]
        lines.append(
            f"| `{outcome['case_id']}` | `{outcome['expected']}` | `{baseline_actual}` | "
            f"`{rag_actual}` | {outcome['retrieved_chunks']} |"
        )
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "This is an experimental two-pass flow: the full-CV agent run supplies requirement "
            "queries, then the same agent runs again on retrieved CV chunks. Baseline uses one "
            "generation call; RAG uses up to two, so this is not yet a latency- or cost-neutral "
            "production design. The 24 hand-authored synthetic resume/JD pairs are short and do "
            "not represent the user's full career history; retrieval quality and verdict labels "
            "must be validated on longer, independently reviewed profiles before enabling it in "
            "the application. Similarity is a retrieval signal, not evidence that a requirement "
            "is satisfied.",
            "",
        ]
    )
    return "\n".join(lines)


async def _run(
    dataset: Path,
    output_path: Path,
    *,
    top_k_per_query: int,
    max_chunks: int,
    minimum_similarity: float,
    retrieval_strategy: str,
) -> int:
    cases = load_cases(dataset)
    settings = get_settings()
    agent = get_agent("matching_agent")
    outcomes = await evaluate_rag_cases(
        cases,
        agent,
        top_k_per_query=top_k_per_query,
        max_chunks=max_chunks,
        minimum_similarity=minimum_similarity,
        retrieval_strategy=retrieval_strategy,
    )
    report = render_rag_report(
        cases,
        outcomes,
        provider=settings.llm_provider,
        model=(
            f"{settings.ollama_model} + {settings.ollama_secondary_model}"
            if settings.llm_provider == "ollama_ensemble"
            else settings.ollama_model
            if settings.llm_provider == "ollama"
            else settings.anthropic_model
        ),
        top_k_per_query=top_k_per_query,
        max_chunks=max_chunks,
        minimum_similarity=minimum_similarity,
        retrieval_strategy=retrieval_strategy,
    )
    output_path.write_text(report, encoding="utf-8")
    print(report)
    return int(
        any(
            outcome["baseline"]["status"] == "error"
            or outcome["rag"]["status"] == "error"
            for outcome in outcomes
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--top-k-per-query", type=int, default=1)
    parser.add_argument("--max-chunks", type=int, default=12)
    parser.add_argument("--minimum-similarity", type=float, default=0.25)
    parser.add_argument(
        "--retrieval-strategy",
        choices=("dense", "hybrid"),
        default="hybrid",
        help="dense is the previous embedding-only retriever; hybrid adds BM25 and explainable reranking.",
    )
    args = parser.parse_args()
    if args.top_k_per_query < 1 or args.max_chunks < 1:
        parser.error("--top-k-per-query and --max-chunks must be positive.")
    if not 0 <= args.minimum_similarity <= 1:
        parser.error("--minimum-similarity must be between 0 and 1.")
    try:
        sys.exit(
            asyncio.run(
                _run(
                    args.dataset,
                    args.output,
                    top_k_per_query=args.top_k_per_query,
                    max_chunks=args.max_chunks,
                    minimum_similarity=args.minimum_similarity,
                    retrieval_strategy=args.retrieval_strategy,
                )
            )
        )
    except EmbeddingCallError as exc:
        parser.exit(1, f"Embedding retrieval failed: {exc}\n")


if __name__ == "__main__":
    main()
