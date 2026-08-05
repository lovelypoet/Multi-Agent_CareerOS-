"""Test parser của integrations/itviec.py — chạy trên fixture HTML đã lưu sẵn, KHÔNG gọi
mạng thật. Fixture được trích trực tiếp (verbatim) từ 1 lần fetch thật trang
https://itviec.com/it-jobs/data-engineer và 1 trang detail thật, xem comment trong
tests/fixtures/*.html.
"""

from __future__ import annotations

from pathlib import Path

from app.integrations.itviec import CATEGORY_URLS, parse_detail_html, parse_listing_html

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestParseListingHtml:
    def test_parses_all_cards(self):
        html = (FIXTURES_DIR / "itviec_listing.html").read_text(encoding="utf-8")
        jobs = parse_listing_html(html)
        assert len(jobs) == 3

    def test_extracts_title_company_url_tags(self):
        html = (FIXTURES_DIR / "itviec_listing.html").read_text(encoding="utf-8")
        jobs = parse_listing_html(html)
        first = jobs[0]
        assert "Data Engineer" in first.title
        assert first.company == "Techcombank"
        assert first.url == "https://itviec.com/it-jobs/expert-senior-officer-data-engineer-techcombank-2329"
        assert "Data Engineer" in first.skill_tags
        assert "ETL" in first.skill_tags

    def test_url_has_no_tracking_query_string(self):
        """ITviec gắn ?lab_feature=... vào href hiển thị — url dùng để dedup phải sạch."""
        html = (FIXTURES_DIR / "itviec_listing.html").read_text(encoding="utf-8")
        jobs = parse_listing_html(html)
        for job in jobs:
            assert "?" not in job.url

    def test_empty_html_returns_empty_list(self):
        assert parse_listing_html("<html><body></body></html>") == []


class TestParseDetailHtml:
    def test_extracts_full_description_text(self):
        html = (FIXTURES_DIR / "itviec_detail.html").read_text(encoding="utf-8")
        description = parse_detail_html(html)
        assert "Job description" in description
        assert "Data Architecture" in description
        # Job thật này có yêu cầu 4+ năm kinh nghiệm — dùng làm test case cho level filter.
        assert "4+ years" in description

    def test_missing_job_content_raises(self):
        from app.integrations.itviec import ItviecFetchError
        import pytest

        with pytest.raises(ItviecFetchError):
            parse_detail_html("<html><body><p>no job-content block here</p></body></html>")


class TestCategoryUrls:
    def test_all_seven_categories_present(self):
        expected = {
            "Data Engineer",
            "AI / Machine Learning Engineer",
            "Computer Vision Engineer",
            "Embedded Engineer",
            "Firmware Engineer",
            "Real-Time Systems Engineer",
            "Hardware-Software Integration Engineer",
        }
        assert set(CATEGORY_URLS.keys()) == expected

    def test_urls_point_at_itviec_it_jobs(self):
        for url in CATEGORY_URLS.values():
            assert url.startswith("https://itviec.com/it-jobs/")
