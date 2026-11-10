"""Remote OK's public JSON feed integration."""

from __future__ import annotations

import logging
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.integrations.job_listing import JobListing

logger = logging.getLogger(__name__)

API_URL = "https://remoteok.com/api"
BASE_URL = "https://remoteok.com"
USER_AGENT = "CareerOS-JobFetcher/1.0 (personal job-matching tool, not affiliated with Remote OK)"
REQUEST_TIMEOUT_SECONDS = 20.0


class RemoteOKFetchError(RuntimeError):
    """Raised when Remote OK cannot be reached or its response is invalid."""


def _remote_job_url(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None

    url = urljoin(BASE_URL, value.strip())
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {"remoteok.com", "www.remoteok.com"}
        or not parsed.path.startswith("/remote-jobs/")
    ):
        return None
    return url


def _plain_text(value: str) -> str:
    return BeautifulSoup(value, "html.parser").get_text(separator="\n", strip=True)


def parse_remoteok_response(payload: object) -> list[JobListing]:
    """Normalize valid job entries; skip feed metadata and malformed individual records."""
    if not isinstance(payload, list):
        raise RemoteOKFetchError("Remote OK returned an unexpected response shape.")

    jobs: list[JobListing] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            logger.warning("[remoteok] Skipping non-object feed entry at index %d.", index)
            continue

        title = item.get("position")
        description = item.get("description")
        url = _remote_job_url(item.get("url"))
        raw_tags = item.get("tags", [])
        if not isinstance(title, str) or not title.strip() or not isinstance(description, str) or not url:
            continue
        if not isinstance(raw_tags, list):
            raw_tags = []
        tags = [tag.strip() for tag in raw_tags if isinstance(tag, str) and tag.strip()]
        description_text = _plain_text(description)
        if not description_text:
            continue

        raw_company = item.get("company")
        company = raw_company.strip() if isinstance(raw_company, str) and raw_company.strip() else None
        jobs.append(
            JobListing(
                title=title.strip(),
                company=company,
                url=url,
                skill_tags=tags,
                description=description_text,
            )
        )
    return jobs


async def fetch_jobs() -> list[JobListing]:
    """Fetch Remote OK's public API once and return normalized job descriptions."""
    try:
        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        ) as client:
            response = await client.get(API_URL)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise RemoteOKFetchError(f"Could not fetch Remote OK jobs: {exc}") from exc

    return parse_remoteok_response(payload)
