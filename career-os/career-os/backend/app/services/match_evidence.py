"""Verify model-provided source quotes and derive a conservative match score."""

from __future__ import annotations

import re

from app.schemas.match import JDAnalysis, JDRequirement, MatchOutput, RequirementAssessment

_TOKEN_RE = re.compile(r"[\w.+#-]+", re.UNICODE)
_STOPWORDS = {
    "a",
    "an",
    "and",
    "or",
    "the",
    "of",
    "to",
    "in",
    "for",
    "with",
    "on",
    "at",
    "is",
    "are",
    "be",
    "have",
    "has",
    "had",
    "as",
    "by",
    "from",
    "that",
    "this",
    "it",
    "years",
    "year",
    "yrs",
    "yr",
    "minimum",
    "required",
    "requirement",
    "must",
    "preferred",
    "nice",
    "plus",
    "strong",
    "advanced",
    "proficient",
    "proficiency",
    "experience",
    "experienced",
    "knowledge",
    "familiarity",
    "ability",
    "working",
    "hands",
    "similar",
    "framework",
    "skills",
    "skill",
    "development",
    "developing",
    "professional",
}
_NEGATION_RE = re.compile(
    r"\b(?:no|not|never|without|haven['’]?t|hasn['’]?t|didn['’]?t|lack(?:s|ing)?)\b",
    re.IGNORECASE,
)
_LIMITATION_RE = re.compile(
    r"\b(?:basic|beginner|limited|introductory|course|tutorial|personal project|once|briefly)\b",
    re.IGNORECASE,
)
_EXPERIENCE_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b", re.IGNORECASE
)
_LIST_SPLIT_RE = re.compile(r"\s*(?:,|;|\band\b|\bor\b)\s*", re.IGNORECASE)
_LABEL_PREFIX_RE = re.compile(
    r"^(?:(?:required|must[- ]have|preferred|nice[- ]to[- ]have|bonus)\s*:\s*)+",
    re.IGNORECASE,
)
_EXPERIENCE_WORDS = {
    "year",
    "years",
    "yr",
    "yrs",
    "experience",
    "professional",
    "production",
    "hands",
    "on",
    "minimum",
    "at",
    "least",
    "of",
}
_KNOWN_TECHNOLOGIES = (
    "React",
    "ReactJS",
    "TypeScript",
    "JavaScript",
    "Python",
    "Java",
    "C++",
    "C#",
    "Go",
    "Rust",
    "Kotlin",
    "Swift",
    "PHP",
    "Ruby",
    "Scala",
    "SQL",
    "HTML",
    "CSS",
    "Next.js",
    "Node.js",
    "Django",
    "FastAPI",
    "Flask",
    "Spring",
    ".NET",
    "Angular",
    "Vue",
    "Svelte",
    "Express",
    "NestJS",
    "PostgreSQL",
    "Postgres",
    "MySQL",
    "MongoDB",
    "Redis",
    "Elasticsearch",
    "Kafka",
    "RabbitMQ",
    "Spark",
    "Hadoop",
    "Airflow",
    "dbt",
    "Snowflake",
    "BigQuery",
    "Redshift",
    "Databricks",
    "AWS",
    "Azure",
    "GCP",
    "Kubernetes",
    "Docker",
    "Terraform",
    "Ansible",
    "Linux",
    "Jenkins",
    "Prometheus",
    "Grafana",
    "Selenium",
    "Playwright",
    "Cypress",
    "Jest",
    "PyTorch",
    "TensorFlow",
    "Keras",
    "OpenCV",
    "LangChain",
    "LlamaIndex",
    "RAG",
    "LLM",
    "NLP",
    "MATLAB",
    "ROS",
    "ROS2",
    "RTOS",
)
_LIMITATION_PHRASES = (
    "basic",
    "beginner",
    "limited",
    "introductory",
    "short course",
    "online course",
    "tutorial",
    "personal project",
    "personal projects",
    "once",
    "no experience",
    "not listed",
    "has not",
    "have not",
    "never used",
)


def _normalized(text: str) -> str:
    return " ".join(text.casefold().split())


def _contains_quote(document: str, quote: str) -> bool:
    normalized_quote = _normalized(quote)
    return bool(normalized_quote) and normalized_quote in _normalized(document)


def _tokens(text: str) -> set[str]:
    tokens = set()
    for token in _TOKEN_RE.findall(text.casefold()):
        cleaned = token.strip(".-")
        if cleaned.endswith("s") and len(cleaned) > 4 and not cleaned.endswith("ss"):
            cleaned = cleaned[:-1]
        if (
            cleaned
            and cleaned not in _STOPWORDS
            and not cleaned.replace("+", "").isdigit()
        ):
            tokens.add(cleaned)
    return tokens


def _key_terms(requirement_text: str) -> set[str]:
    return _tokens(requirement_text) - _EXPERIENCE_WORDS


def _years(text: str) -> float | None:
    match = _EXPERIENCE_RE.search(text)
    return float(match.group(1)) if match else None


def _contains_term(text: str, term: str) -> bool:
    escaped = re.escape(term.strip())
    return bool(escaped) and re.search(rf"(?<!\w){escaped}(?!\w)", text, re.IGNORECASE) is not None


def _expand_requirement(requirement: JDRequirement, tech_stack: list[str]) -> list[JDRequirement]:
    """Split model-grouped lists into independently assessable JD criteria."""
    quote = requirement.jd_quote
    source = f"{requirement.text} {quote}"
    candidate_technologies = list(dict.fromkeys([*tech_stack, *_KNOWN_TECHNOLOGIES]))
    technologies = [
        technology.strip()
        for technology in candidate_technologies
        if technology.strip() and _contains_term(source, technology.strip())
    ]
    technologies.sort(
        key=lambda technology: re.search(
            rf"(?<!\w){re.escape(technology)}(?!\w)", source, re.IGNORECASE
        ).start()
    )

    expanded: list[JDRequirement] = []
    seen: set[tuple[str, str]] = set()

    def add(text: str, category: str, priority: str = requirement.priority) -> None:
        cleaned = text.strip(" \t\r\n:.-")
        key = (category, _normalized(cleaned))
        if not cleaned or key in seen:
            return
        seen.add(key)
        expanded.append(
            JDRequirement(
                text=cleaned,
                priority=priority,
                category=category,
                jd_quote=quote,
            )
        )

    required_years = _years(source)
    if required_years is not None:
        # Keep the domain terms alongside the threshold so evidence must establish relevant
        # experience, not merely an unrelated number of years elsewhere in the resume.
        first_technology = technologies[0] if technologies else None
        context_source = requirement.text
        if first_technology:
            match = re.search(
                rf"(?<!\w){re.escape(first_technology)}(?!\w)",
                context_source,
                re.IGNORECASE,
            )
            if match:
                context_source = context_source[: match.start()]
        context = _EXPERIENCE_RE.sub("", context_source)
        context = _LABEL_PREFIX_RE.sub("", context)
        context = re.sub(r"\b(?:and|or)\b", " ", context, flags=re.IGNORECASE)
        context = " ".join(context.split()).strip(" ,;:-.")
        context_terms = _key_terms(context)
        if not context_terms and first_technology:
            context = first_technology
        elif not context_terms:
            context = "relevant experience"
        add(f"{required_years:g}+ years {context or 'relevant experience'}", "experience")

    for technology in technologies:
        add(technology, "skill")

    if not technologies and required_years is None:
        raw_parts = _LIST_SPLIT_RE.split(_LABEL_PREFIX_RE.sub("", requirement.text))
        parts = [part.strip(" \t\r\n:.-") for part in raw_parts if part.strip(" \t\r\n:.-")]
        if len(parts) > 1:
            for part in parts:
                add(part, requirement.category)
        else:
            add(requirement.text, requirement.category)

    if not expanded:
        add(requirement.text, requirement.category)
    return expanded


def _candidate_evidence(resume_text: str, quote: str) -> list[str]:
    candidates = []
    candidates.extend(
        line.strip()
        for line in re.split(r"(?<=[.!?])\s+|\r?\n+", resume_text)
        if line.strip()
    )
    if quote and _contains_quote(resume_text, quote):
        candidates.insert(0, quote)
    return candidates


def _is_explicitly_negated(candidate: str, requirement_text: str) -> bool:
    terms = _key_terms(requirement_text)
    for term in terms:
        pattern = re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)
        for match in pattern.finditer(candidate):
            before = candidate[max(0, match.start() - 50) : match.start()]
            after = candidate[match.end() : min(len(candidate), match.end() + 40)]
            if re.search(r"\b(?:no|not|never|without|haven['’]?t|hasn['’]?t|didn['’]?t|lack\w*)\b[^.!?;]{0,40}$", before, re.I):
                return True
            if re.search(r"^[^.!?;]{0,40}\b(?:not listed|no experience|never used)\b", after, re.I):
                return True
    return False


def _verify_requirement_evidence(
    *,
    requirement_text: str,
    category: str,
    status: str,
    quote: str,
    resume_text: str,
) -> tuple[str, str]:
    terms = _key_terms(requirement_text)
    required_years = _years(requirement_text) if category == "experience" else None
    best_quote = ""
    best_coverage = 0.0
    best_years: float | None = None
    relevant_tokens = terms

    for candidate in _candidate_evidence(resume_text, quote):
        candidate_terms = _tokens(candidate)
        if _is_explicitly_negated(candidate, requirement_text):
            continue
        coverage = len(terms & candidate_terms) / len(terms) if terms else 1.0
        candidate_years = _years(candidate)
        if required_years is not None and candidate_years is None:
            coverage *= 0.5
        if coverage > best_coverage:
            best_quote = candidate
            best_coverage = coverage
            best_years = candidate_years

    if not best_quote or best_coverage == 0:
        return "missing", ""

    if required_years is not None:
        context_terms = relevant_tokens
        if best_years is None:
            return ("partial", best_quote) if best_coverage >= 0.5 else ("missing", "")
        if best_years < required_years:
            return "partial", best_quote
        if context_terms and not context_terms.intersection(_tokens(best_quote)):
            return "missing", ""

    if _LIMITATION_RE.search(best_quote) or any(
        phrase in best_quote.casefold() for phrase in _LIMITATION_PHRASES
    ):
        return "partial", best_quote
    if status == "missing":
        if best_coverage >= 1:
            return "met", best_quote
        if best_coverage >= 0.5:
            return "partial", best_quote
        return "missing", ""
    if status == "met" and best_coverage < 1:
        return ("partial", best_quote) if best_coverage >= 0.5 else ("missing", "")
    if status == "partial" and best_coverage < 0.5:
        return "missing", ""
    return status, best_quote


def _verdict_for_score(score: int) -> str:
    if score >= 85:
        return "strong_match"
    if score >= 65:
        return "good_match"
    if score >= 40:
        return "partial_match"
    return "weak_match"


def verify_and_score_match(
    output: MatchOutput,
    *,
    resume_text: str,
    job_description_text: str,
) -> MatchOutput:
    """Keep only quoted JD requirements, verify CV quotes, and score by fixed weights.

    Outputs without structured requirements are retained as legacy results for old stored
    prompts and compatibility; they are explicitly labeled so they are not represented as
    evidence-checked analyses.
    """
    analysis = output.jd_analysis
    if analysis is None:
        return output.model_copy(update={"requirement_assessments": []})

    indexed_requirements = []
    seen_requirements: set[tuple[str, str, str]] = set()
    for index, requirement in enumerate(analysis.requirements):
        if not _contains_quote(job_description_text, requirement.jd_quote):
            continue
        for expanded in _expand_requirement(requirement, analysis.tech_stack):
            key = (
                expanded.priority,
                expanded.category,
                _normalized(expanded.text),
            )
            if key not in seen_requirements:
                indexed_requirements.append((index, expanded))
                seen_requirements.add(key)
    if not indexed_requirements:
        raise ValueError("The JD analysis contains no requirement quote found in the job description.")

    valid_assessments: dict[int, RequirementAssessment] = {}
    for assessment in output.requirement_assessments:
        if assessment.requirement_index >= len(analysis.requirements):
            continue
        if assessment.requirement_index not in valid_assessments:
            valid_assessments[assessment.requirement_index] = assessment

    verified_requirements = []
    verified_assessments = []
    matched: list[str] = []
    missing: list[str] = []
    weighted_total = 0.0
    weighted_earned = 0.0

    for original_index, requirement in indexed_requirements:
        weight = 2 if requirement.priority == "required" else 1
        weighted_total += weight
        assessment = valid_assessments.get(original_index)
        status, evidence = _verify_requirement_evidence(
            requirement_text=requirement.text,
            category=requirement.category,
            status=assessment.status if assessment is not None else "missing",
            quote=assessment.cv_evidence if assessment is not None else "",
            resume_text=resume_text,
        )
        if status == "missing":
            evidence = ""
            missing.append(requirement.text)
        else:
            if status == "met":
                matched.append(requirement.text)
                weighted_earned += weight
            else:
                missing.append(requirement.text)
                weighted_earned += weight * 0.5

        new_index = len(verified_requirements)
        verified_requirements.append(requirement)
        verified_assessments.append(
            RequirementAssessment(
                requirement_index=new_index,
                status=status,
                cv_evidence=evidence,
            )
        )

    score = round(100 * weighted_earned / weighted_total) if weighted_total else 0
    verified_analysis = JDAnalysis(
        role_title=analysis.role_title,
        experience_level=analysis.experience_level,
        tech_stack=analysis.tech_stack,
        requirements=verified_requirements,
    )
    ratio = f"{weighted_earned:g}/{weighted_total:g} weighted requirement points"
    reasoning = f"Evidence-checked score: {ratio}. {output.reasoning}"

    return output.model_copy(
        update={
            "score": score,
            "verdict": _verdict_for_score(score),
            "matched_requirements": matched,
            "missing_requirements": missing,
            "jd_analysis": verified_analysis,
            "requirement_assessments": verified_assessments,
            "analysis_basis": "evidence_based",
            "reasoning": reasoning,
        }
    )
