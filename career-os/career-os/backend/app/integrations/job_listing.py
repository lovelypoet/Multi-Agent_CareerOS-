"""Normalized listing fields shared by job-source integrations."""

from dataclasses import dataclass, field


@dataclass(slots=True)
class JobListing:
    title: str
    company: str | None
    url: str
    skill_tags: list[str] = field(default_factory=list)
    description: str | None = None
