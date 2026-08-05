"""Nơi DUY NHẤT trong codebase import `pypdf`, cùng triết lý với `integrations/anthropic.py`
và `integrations/itviec.py`.

Nhận sẵn `bytes` (không biết gì về `UploadFile`/stream) — việc đọc file đúng cách (đọc 1 lần
duy nhất) là trách nhiệm của endpoint gọi hàm này, xem `api/resume.py`.
"""

from __future__ import annotations

import io

import pypdf

MIN_TEXT_CHARS = 50


class PdfExtractionError(RuntimeError):
    """Lỗi trích xuất PDF nói chung — không lộ exception thô của pypdf ra ngoài API."""


class PdfEncryptedError(PdfExtractionError):
    """File PDF có mật khẩu, không đọc được nội dung."""


class PdfEmptyTextError(PdfExtractionError):
    """Đọc được file nhưng không trích ra được text đủ dài (thường là PDF scan ảnh)."""


class PdfParseError(PdfExtractionError):
    """File PDF hỏng hoặc pypdf không đọc được vì lý do khác."""


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Trích text từ nội dung PDF. Ném lỗi rõ ràng thay vì trả về text rỗng/rác."""
    try:
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    except Exception as exc:  # file hỏng, không phải PDF hợp lệ theo pypdf...
        raise PdfParseError(f"Không đọc được file PDF: {exc}") from exc

    # Kiểm tra chủ động NGAY sau khi mở, không đợi exception giữa chừng lúc extract.
    if reader.is_encrypted:
        raise PdfEncryptedError(
            "File PDF có mật khẩu. Hãy gỡ mật khẩu trước khi upload, hoặc dán text thủ công."
        )

    try:
        pages_text = [page.extract_text() for page in reader.pages]
    except pypdf.errors.FileNotDecryptedError as exc:
        # Lưới an toàn — is_encrypted ở trên đã bắt hầu hết trường hợp.
        raise PdfEncryptedError(
            "File PDF có mật khẩu. Hãy gỡ mật khẩu trước khi upload, hoặc dán text thủ công."
        ) from exc
    except Exception as exc:
        raise PdfParseError(f"Không đọc được nội dung file PDF: {exc}") from exc

    text = "\n".join(pages_text).strip()

    # extract_text() trả '' cho PDF scan ảnh (không có text layer) — KHÔNG throw exception,
    # phải tự kiểm tra độ dài, không dựa vào try/except cho case này.
    if len(text) < MIN_TEXT_CHARS:
        raise PdfEmptyTextError(
            "Không trích được nội dung từ file này, có thể đây là file scan ảnh — hãy dán "
            "text thủ công."
        )

    return text
