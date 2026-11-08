"""Evaluate the matching agent against current ITviec AI job listings and synthetic profiles."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from app.core.agent_contract import AgentExecutionError
from app.core.agent_registry import get_agent
from app.core.config import get_settings
from app.integrations.itviec import (
    CATEGORY_URLS,
    ItviecFetchError,
    JobListingMeta,
    fetch_detail,
    fetch_listing,
)
from app.scripts.evaluate_matching import EvaluationCase, evaluate_cases, render_report

JOB_CATEGORY = "AI / Machine Learning Engineer"
JOB_COUNT = 3
PROFILE_VERDICTS = ("strong_match", "good_match", "partial_match", "weak_match")


def select_diverse_listings(
    listings: list[JobListingMeta],
    *,
    limit: int = JOB_COUNT,
) -> list[JobListingMeta]:
    if limit < 1:
        raise ValueError("limit must be at least one.")

    selected: list[JobListingMeta] = []
    seen_urls: set[str] = set()
    seen_companies: set[str] = set()
    for listing in listings:
        company_key = (listing.company or listing.url).strip().casefold()
        if listing.url in seen_urls or company_key in seen_companies:
            continue
        seen_urls.add(listing.url)
        seen_companies.add(company_key)
        selected.append(listing)
        if len(selected) == limit:
            break
    return selected


def build_synthetic_cases(
    listings: list[JobListingMeta],
    descriptions: dict[str, str],
) -> list[EvaluationCase]:
    cases: list[EvaluationCase] = []
    for index, listing in enumerate(listings, start=1):
        description = descriptions.get(listing.url)
        if not description:
            raise ValueError(f"Missing live job description for {listing.url}")
        if len(listing.skill_tags) < 2:
            raise ValueError(f"Need at least two listing skill tags to build profiles: {listing.url}")

        skills = listing.skill_tags
        skills_text = ", ".join(skills)
        missing_skill = skills[-1]
        good_skills = ", ".join(skills[:-1])
        partial_skills = ", ".join(skills[: max(1, len(skills) // 3)])
        profiles = [
            (
                "strong_match",
                f"AI engineer with 10 years of professional production experience. Led deployed "
                f"systems in roles directly related to {listing.title}. Strong hands-on experience "
                f"with every advertised skill: {skills_text}.",
                "Designed strong profile: senior relevant experience and evidence for all listing skills.",
            ),
            (
                "good_match",
                f"AI engineer with 8 years of professional production experience in work related to "
                f"{listing.title}. Strong hands-on experience with {good_skills}. No experience with "
                f"{missing_skill}.",
                "Designed good profile: substantial relevant experience and most listing skills, with one stated gap.",
            ),
            (
                "partial_match",
                f"Junior software engineer with one year of internship and personal-project experience. "
                f"Has tried {partial_skills} in small prototypes, but has no professional AI-system "
                f"deployment experience and no evidence for the other advertised skills.",
                "Designed partial profile: adjacent foundation and limited skill overlap, but major experience and skill gaps.",
            ),
            (
                "weak_match",
                "Office administrator with eight years coordinating schedules, records, and vendors. "
                "Uses spreadsheets for routine tracking and has no professional software, AI, or "
                "machine-learning experience.",
                "Designed weak profile: no relevant software or AI experience.",
            ),
        ]
        for verdict, resume_text, rationale in profiles:
            cases.append(
                EvaluationCase(
                    case_id=f"job_{index}_{verdict}",
                    resume_text=resume_text,
                    job_description=description,
                    expected_verdict=verdict,
                    rationale=rationale,
                )
            )
    return cases


def render_live_report(
    cases: list[EvaluationCase],
    outcomes: list[dict],
    *,
    provider: str,
    listings: list[JobListingMeta],
) -> str:
    report = render_report(cases, outcomes, provider=provider)
    report, _ = report.split("\n## Interpretation\n", maxsplit=1)
    lines = [
        "## Interpretation",
        "",
        "This exploratory benchmark uses current live ITviec descriptions with controlled synthetic "
        "profiles. Its labels were assigned from the profile construction, not independently "
        "adjudicated by hiring experts. The score measures performance on these scenarios only and "
        "is not a real-world applicant-matching accuracy estimate.",
        "",
        "## Live source postings",
        "",
        "Job descriptions were fetched from ITviec at run time, used in memory, and not copied into this report.",
        "",
        "| Company | Listing | URL |",
        "|---|---|---|",
    ]
    for listing in listings:
        title = listing.title.replace("|", "\\|")
        company = (listing.company or "Not listed").replace("|", "\\|")
        url = listing.url.replace("|", "%7C")
        lines.append(f"| {company} | {title} | {url} |")
    lines.extend(
        [
            "",
            "## Benchmark limitations",
            "",
            "This is an exploratory controlled benchmark, not independently adjudicated ground truth. "
            "The synthetic profile labels are assigned by construction (full skill coverage, one "
            "advertised-skill gap, limited overlap, or unrelated experience). Listing tags may not "
            "map exactly to must-have versus preferred requirements in the full posting. Use this "
            "to inspect behavior on current real postings, not as a CV accuracy claim.",
            "",
        ]
    )
    return f"{report}\n" + "\n".join(lines)


async def _run(output_path: Path | None) -> int:
    listings = select_diverse_listings(await fetch_listing(CATEGORY_URLS[JOB_CATEGORY]))
    if len(listings) != JOB_COUNT:
        raise ItviecFetchError(
            f"Expected {JOB_COUNT} distinct-company listings in {JOB_CATEGORY}, found {len(listings)}."
        )

    descriptions = {listing.url: await fetch_detail(listing.url) for listing in listings}
    cases = build_synthetic_cases(listings, descriptions)
    outcomes = await evaluate_cases(cases, get_agent("matching_agent"))
    report = render_live_report(
        cases,
        outcomes,
        provider=get_settings().llm_provider,
        listings=listings,
    )
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
    print(report)
    return 1 if any(outcome["status"] == "error" for outcome in outcomes) else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Also write the report to this path.")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        sys.exit(asyncio.run(_run(args.output)))
    except AgentExecutionError as exc:
        raise SystemExit(f"Agent evaluation failed: {exc}") from exc


if __name__ == "__main__":
    main()
