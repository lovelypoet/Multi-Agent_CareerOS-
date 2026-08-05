"""Nơi DUY NHẤT trong codebase gọi HTTP tới ITviec và parse HTML.

Cùng triết lý với `integrations/anthropic.py` (nơi duy nhất gọi Anthropic SDK): không file
nào khác được gọi httpx/requests tới itviec.com.

Đã kiểm tra `https://itviec.com/robots.txt` trước khi viết file này — chỉ disallow
`/subscriptions/new`, không áp dụng cho `/it-jobs/...`. Selector bên dưới được rút ra từ
khảo sát HTML thật (xem `tests/fixtures/itviec_*.html`, lưu lại đúng lúc khảo sát), không
đoán class name.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://itviec.com"

# Personal tool, không giả làm trình duyệt để né chặn.
USER_AGENT = "CareerOS-JobFetcher/1.0 (personal job-matching tool, not affiliated with ITviec)"

REQUEST_TIMEOUT_SECONDS = 20.0
# Delay lịch sự giữa các request tới ITviec — áp dụng sau MỌI request (listing lẫn detail).
REQUEST_DELAY_SECONDS = 1.5

# Đã xác nhận thủ công từng URL qua khảo sát menu "Jobs by Expertise" trên trang thật
# (không đoán slug từ tên category). Nếu ITviec đổi slug sau này, category đó sẽ trả 404 —
# fetch_jobs.py phải bắt lỗi per-category, log lại, và bỏ qua, không dừng cả pipeline.
CATEGORY_URLS: dict[str, str] = {
    "Data Engineer": f"{BASE_URL}/it-jobs/data-engineer",
    "AI / Machine Learning Engineer": f"{BASE_URL}/it-jobs/ai-machine-learning-engineer",
    "Computer Vision Engineer": f"{BASE_URL}/it-jobs/computer-vision-engineer",
    "Embedded Engineer": f"{BASE_URL}/it-jobs/embedded-engineer",
    "Firmware Engineer": f"{BASE_URL}/it-jobs/firmware-engineer",
    "Real-Time Systems Engineer": f"{BASE_URL}/it-jobs/real-time-systems-engineer",
    "Hardware-Software Integration Engineer": f"{BASE_URL}/it-jobs/hardware-software-integration-engineer",
}


class ItviecFetchError(RuntimeError):
    """Gọi HTTP tới ITviec thất bại (mạng, timeout, status lỗi) hoặc parse ra thiếu dữ liệu."""


@dataclass(slots=True)
class JobListingMeta:
    """Metadata rẻ lấy được từ listing page — không có level_text (xem prompt Phase 1 mục 3:
    ITviec không hiển thị field level riêng trên listing, level phải suy từ title + detail).
    """

    title: str
    company: str | None
    url: str
    skill_tags: list[str] = field(default_factory=list)


def _clean_job_url(href: str) -> str:
    """Chuẩn hoá URL job về dạng không query string — dùng làm khoá dedup ổn định.

    ITviec gắn tracking param (`lab_feature=...`) vào href hiển thị trên listing; nếu dùng
    nguyên href đó để dedup, cùng 1 job có thể bị coi là "mới" nhiều lần chỉ vì query khác.
    """
    clean = href.split("?", 1)[0]
    if clean.startswith("/"):
        clean = f"{BASE_URL}{clean}"
    return clean


def parse_listing_html(html: str) -> list[JobListingMeta]:
    """Parse 1 trang listing (`.job-card` × N) thành metadata. Hàm thuần, không gọi mạng —
    để test được offline bằng fixture.
    """
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[JobListingMeta] = []

    for card in soup.select(".job-card"):
        title_link = card.select_one("h3 a")
        if title_link is None:
            continue
        title = title_link.get_text(strip=True)

        # Ưu tiên slug trong data-attribute (không có query tracking) hơn href hiển thị.
        slug = card.get("data-search--job-selection-job-slug-value")
        href = title_link.get("href")
        if slug:
            url = f"{BASE_URL}/it-jobs/{slug}"
        elif href:
            url = _clean_job_url(href)
        else:
            continue

        # Mỗi card có 2 link /companies/...: 1 cái bọc logo (text rỗng), 1 cái có tên công ty.
        company = None
        for a in card.select('a[href*="/companies/"]'):
            text = a.get_text(strip=True)
            if text:
                company = text
                break

        skill_tags = [tag.get_text(strip=True) for tag in card.select(".itag") if tag.get_text(strip=True)]

        jobs.append(JobListingMeta(title=title, company=company, url=url, skill_tags=skill_tags))

    return jobs


def parse_detail_html(html: str) -> str:
    """Parse trang detail, trả về full description dạng text thô (`.job-content`).

    Khối `.job-content` gồm Job description + Skills + Job Expertise + phần "why you'll love
    working here" — đủ ngữ cảnh cho cả level-filter lẫn matching_agent, không lẫn sidebar
    ("More jobs for you"...).
    """
    soup = BeautifulSoup(html, "html.parser")
    content = soup.select_one(".job-content")
    if content is None:
        raise ItviecFetchError("Không tìm thấy khối mô tả job (.job-content) trên trang detail.")
    return content.get_text(separator="\n", strip=True)


async def _get(client: httpx.AsyncClient, url: str) -> str:
    try:
        response = await client.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ItviecFetchError(f"Không fetch được {url}: {exc}") from exc
    finally:
        # Delay lịch sự sau MỌI request, kể cả khi lỗi, để không dồn dập retry.
        await asyncio.sleep(REQUEST_DELAY_SECONDS)
    return response.text


async def fetch_listing(category_url: str) -> list[JobListingMeta]:
    """Fetch trang 1 của 1 category listing. Chỉ lấy metadata rẻ, KHÔNG fetch detail."""
    async with httpx.AsyncClient() as client:
        html = await _get(client, category_url)
    return parse_listing_html(html)


async def fetch_detail(url: str) -> str:
    """Fetch trang chi tiết 1 job, trả về full description text."""
    async with httpx.AsyncClient() as client:
        html = await _get(client, url)
    return parse_detail_html(html)
