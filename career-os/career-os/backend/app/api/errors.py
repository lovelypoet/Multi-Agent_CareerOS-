"""Mã lỗi dùng chung giữa BE và FE.

FE dựa vào `code` để quyết định hiển thị gì (ví dụ RESUME_NOT_FOUND thì hiện nút sang trang lưu
resume), chứ không so khớp chuỗi message — message có thể đổi bất cứ lúc nào.
"""

from __future__ import annotations

from fastapi import HTTPException


class ErrorCode:
    RESUME_NOT_FOUND = "RESUME_NOT_FOUND"
    AGENT_FAILED = "AGENT_FAILED"
    AGENT_UNAVAILABLE = "AGENT_UNAVAILABLE"
    AGENT_MISCONFIGURED = "AGENT_MISCONFIGURED"
    # Phase 2 — approval & tracking
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    # Phase 2 — upload CV dạng PDF
    PDF_TOO_LARGE = "PDF_TOO_LARGE"
    PDF_NOT_A_PDF = "PDF_NOT_A_PDF"
    PDF_ENCRYPTED = "PDF_ENCRYPTED"
    PDF_EMPTY_TEXT = "PDF_EMPTY_TEXT"
    PDF_PARSE_FAILED = "PDF_PARSE_FAILED"


def api_error(status_code: int, code: str, message: str, **extra: object) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, **extra},
    )
