"""Experimental, in-memory retrieval of resume evidence for a job description."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from app.integrations.embedding_client import cosine_similarity, embed_text

EmbedFunction = Callable[[str], Awaitable[list[float]]]
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\r?\n+")
_TOKEN_RE = re.compile(r"[\w.+#-]+", re.UNICODE)
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
    "have", "in", "is", "it", "of", "on", "or", "the", "to", "with", "years",
    "year", "experience", "experienced", "required", "preferred", "must",
    "knowledge", "skills", "skill",
}
_BM25_K1 = 1.5
_BM25_B = 0.75


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    text: str
    similarity: float
    query: str
    lexical_score: float = 0.0
    rerank_score: float = 0.0


def _tokens(text: str) -> list[str]:
    tokens = []
    for token in _TOKEN_RE.findall(text.casefold()):
        cleaned = token.strip(".-")
        if cleaned.endswith("s") and len(cleaned) > 4 and not cleaned.endswith("ss"):
            cleaned = cleaned[:-1]
        if (
            cleaned
            and cleaned not in _STOPWORDS
            and not cleaned.replace("+", "").isdigit()
        ):
            tokens.append(cleaned)
    return tokens


def _bm25_scores(query: str, chunks: Sequence[str]) -> list[float]:
    query_terms = set(_tokens(query))
    if not query_terms or not chunks:
        return [0.0] * len(chunks)

    documents = [_tokens(chunk) for chunk in chunks]
    average_length = sum(map(len, documents)) / len(documents) or 1.0
    document_frequencies = Counter(
        term for document in documents for term in set(document)
    )
    scores = []
    for document in documents:
        frequencies = Counter(document)
        score = 0.0
        for term in query_terms:
            frequency = frequencies[term]
            if not frequency:
                continue
            inverse_frequency = math.log(
                1 + (len(documents) - document_frequencies[term] + 0.5)
                / (document_frequencies[term] + 0.5)
            )
            denominator = frequency + _BM25_K1 * (
                1 - _BM25_B + _BM25_B * len(document) / average_length
            )
            score += (
                inverse_frequency
                * frequency
                * (_BM25_K1 + 1)
                / denominator
            )
        scores.append(score)
    return scores


def split_resume_chunks(resume_text: str) -> list[str]:
    """Split plain-text resumes into source-preserving sentence/bullet chunks."""
    chunks: list[str] = []
    seen: set[str] = set()
    for candidate in _SENTENCE_BOUNDARY.split(resume_text):
        chunk = " ".join(candidate.split()).strip()
        normalized = chunk.casefold()
        if chunk and normalized not in seen:
            chunks.append(chunk)
            seen.add(normalized)
    return chunks


async def retrieve_resume_chunks(
    resume_text: str,
    queries: Sequence[str],
    *,
    top_k_per_query: int = 1,
    max_chunks: int = 12,
    minimum_similarity: float = 0.25,
    strategy: str = "hybrid",
    embed: EmbedFunction | None = None,
) -> list[RetrievedChunk]:
    """Retrieve and explainably rerank source-preserving resume chunks."""
    if top_k_per_query < 1:
        raise ValueError("top_k_per_query must be at least 1.")
    if max_chunks < 1:
        raise ValueError("max_chunks must be at least 1.")
    if not -1.0 <= minimum_similarity <= 1.0:
        raise ValueError("minimum_similarity must be between -1 and 1.")
    if strategy not in {"dense", "hybrid"}:
        raise ValueError("strategy must be either 'dense' or 'hybrid'.")

    chunks = split_resume_chunks(resume_text)
    distinct_queries = list(dict.fromkeys(query.strip() for query in queries if query.strip()))
    if not chunks or not distinct_queries:
        return []

    embed_text_fn = embed or embed_text
    chunk_vectors = [await embed_text_fn(chunk) for chunk in chunks]
    best_by_chunk: dict[int, RetrievedChunk] = {}

    for query in distinct_queries:
        query_vector = await embed_text_fn(query)
        similarities = [
            cosine_similarity(query_vector, chunk_vector)
            for chunk_vector in chunk_vectors
        ]
        bm25_scores = (
            _bm25_scores(query, chunks)
            if strategy == "hybrid"
            else [0.0] * len(chunks)
        )
        lexical_scores = [
            score / (score + 1.0) if score else 0.0
            for score in bm25_scores
        ]
        query_terms = set(_tokens(query))
        lexical_coverage = [
            len(query_terms.intersection(_tokens(chunk))) / len(query_terms)
            if query_terms
            else 0.0
            for chunk in chunks
        ]
        rerank_scores = [
            (
                0.40 * similarities[index]
                + 0.40 * lexical_scores[index]
                + 0.20 * lexical_coverage[index]
                if strategy == "hybrid"
                else similarities[index]
            )
            for index in range(len(chunks))
        ]
        ranked = sorted(
            range(len(chunks)),
            key=lambda index: (-rerank_scores[index], index),
        )
        selected = 0
        for index in ranked:
            similarity = similarities[index]
            has_lexical_match = lexical_scores[index] > 0
            if similarity < minimum_similarity and not has_lexical_match:
                break
            selected += 1
            current = best_by_chunk.get(index)
            if current is None or rerank_scores[index] > current.rerank_score:
                best_by_chunk[index] = RetrievedChunk(
                    text=chunks[index],
                    similarity=similarity,
                    query=query,
                    lexical_score=lexical_scores[index],
                    rerank_score=rerank_scores[index],
                )
            if selected >= top_k_per_query:
                break

    selected_chunks = sorted(
        best_by_chunk.items(),
        key=lambda item: (-item[1].rerank_score, item[0]),
    )[:max_chunks]
    return [
        RetrievedChunk(
            text=chunk.text,
            similarity=chunk.similarity,
            query=chunk.query,
            lexical_score=chunk.lexical_score,
            rerank_score=chunk.rerank_score,
        )
        for _, chunk in selected_chunks
    ]
