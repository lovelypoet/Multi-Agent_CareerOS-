"""Test `POST /api/resume/upload` — PHẢI gọi qua endpoint thật (`client.post(..., files=...)`),
KHÔNG chỉ unit-test `extract_text_from_pdf()`.

Lý do (xem prompt Phase 2 mục 2.2/10): bug đọc `UploadFile` 2 lần nằm ở TẦNG API (cách đọc
stream), không nằm trong `pdf_extractor.py` (hàm đó chỉ nhận sẵn `bytes`, không biết gì về
stream) — unit test hàm extract với bytes có sẵn sẽ không bao giờ bắt được bug đó.

Fixture PDF được tạo NGAY TRONG TEST bằng `fpdf2`, không commit file nhị phân vào repo.
"""

from __future__ import annotations

import os

import pytest
from fpdf import FPDF

from app.core.db import SessionLocal
from app.models import Resume

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _pdf_with_text(text: str) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 10, text)
    return bytes(pdf.output())


def _blank_pdf() -> bytes:
    pdf = FPDF()
    pdf.add_page()
    return bytes(pdf.output())


def _encrypted_pdf(text: str) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 10, text)
    pdf.set_encryption(owner_password="owner-secret", user_password="user-secret")
    return bytes(pdf.output())


async def _saved_resume_content() -> str | None:
    async with SessionLocal() as session:
        resume = await session.get(Resume, 1)
        return resume.content if resume else None


async def test_valid_pdf_with_text_is_extracted_and_saved(client):
    """Test case quan trọng nhất: nếu code đọc UploadFile 2 lần (bug đã verify), file này sẽ
    thiếu 4 byte header %PDF và pypdf sẽ báo lỗi cho một file hoàn toàn hợp lệ.
    """
    content = _pdf_with_text("3 nam kinh nghiem React, TypeScript co ban, chua co Python. " * 3)

    response = await client.post(
        "/api/resume/upload",
        files={"file": ("cv.pdf", content, "application/pdf")},
    )

    assert response.status_code == 200
    body = response.json()
    assert "React" in body["content"]
    assert "TypeScript" in body["content"]
    assert await _saved_resume_content() == body["content"]


async def test_upload_overwrites_previous_resume_same_singleton_row(client):
    await client.post("/api/resume", json={"content": "Ban dan tay ban dau"})

    content = _pdf_with_text("Noi dung tu PDF, phai ghi de ban dan tay. " * 3)
    response = await client.post(
        "/api/resume/upload",
        files={"file": ("cv.pdf", content, "application/pdf")},
    )

    assert response.status_code == 200
    assert "PDF" in response.json()["content"]

    async with SessionLocal() as session:
        from sqlalchemy import func, select

        count = (await session.execute(select(func.count()).select_from(Resume))).scalar_one()
    assert count == 1  # upsert, không tạo row thứ 2


async def test_pdf_with_no_text_layer_is_rejected(client):
    """CV scan ảnh, không có text layer thật — extract_text() trả '' chứ không throw."""
    content = _blank_pdf()

    response = await client.post(
        "/api/resume/upload",
        files={"file": ("scanned.pdf", content, "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "PDF_EMPTY_TEXT"
    assert await _saved_resume_content() is None


async def test_encrypted_pdf_is_rejected(client):
    content = _encrypted_pdf("Noi dung bi mat, co mat khau. " * 5)

    response = await client.post(
        "/api/resume/upload",
        files={"file": ("locked.pdf", content, "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "PDF_ENCRYPTED"
    assert await _saved_resume_content() is None


async def test_non_pdf_file_renamed_to_pdf_is_rejected(client):
    """Đuôi file .pdf và Content-Type application/pdf đều giả được — phải check magic bytes."""
    content = b"Day chi la file text thuong, khong phai PDF, doi ten thanh .pdf."

    response = await client.post(
        "/api/resume/upload",
        files={"file": ("fake.pdf", content, "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "PDF_NOT_A_PDF"
    assert await _saved_resume_content() is None


async def test_file_over_5mb_rejected_with_413(client):
    # Chỉ cần vượt ngưỡng size check (chạy TRƯỚC khi parse) -- không cần là PDF hợp lệ.
    oversized = b"%PDF-1.3" + os.urandom(5 * 1024 * 1024 + 1024)

    response = await client.post(
        "/api/resume/upload",
        files={"file": ("huge.pdf", oversized, "application/pdf")},
    )

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "PDF_TOO_LARGE"
    assert await _saved_resume_content() is None


async def test_existing_text_endpoint_still_works_unchanged(client):
    """POST /api/resume (Phase 0) không được sửa -- vẫn phải hoạt động y hệt."""
    response = await client.post("/api/resume", json={"content": "Van dan text binh thuong"})
    assert response.status_code == 200
    assert response.json()["content"] == "Van dan text binh thuong"
