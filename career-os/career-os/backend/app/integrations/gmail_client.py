"""Client Gmail API — module DUY NHẤT trong codebase gọi Gmail. Cùng triết lý "1 file, 1 trách
nhiệm, 1 provider/nguồn duy nhất" như `integrations/anthropic.py`, `integrations/itviec.py`.

Chỉ đọc (scope `gmail.readonly`), KHÔNG bao giờ gửi/xoá/sửa — không có method nào trong file này
gọi tới bất kỳ endpoint ghi nào của Gmail API.

Tham số hoá theo `account_email` + `token_path` (không cố định 1 tài khoản) — giống cách
`OllamaClient` tham số hoá theo `model` để hỗ trợ ensemble 2 model cùng lúc; ở đây tham số hoá để
hỗ trợ nhiều tài khoản Gmail cùng lúc (xem `workers/fetch_emails.py`).

KHÔNG BAO GIỜ tự đăng nhập bằng mật khẩu — chỉ đọc file token đã có sẵn (tạo thủ công theo điều
kiện tiên quyết ở đầu prompt) và refresh access token khi hết hạn (dùng refresh_token đã lưu).
Nếu không có token hợp lệ hoặc refresh thất bại, ném lỗi rõ ràng, KHÔNG cố mở luồng đăng nhập
tương tác thay.
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Scope TỐI THIỂU — chỉ đọc, không xin quyền gửi/xoá/sửa email (đã verify đây là scope readonly
# chính thức từ tài liệu Google, không có lý do nghiệp vụ nào cần hơn mức đọc).
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


class GmailAuthError(RuntimeError):
    """Token thiếu/hết hạn/refresh thất bại — KHÔNG BAO GIỜ tự đăng nhập lại bằng mật khẩu, chỉ
    báo lỗi rõ ràng để người dùng tự chạy lại luồng cấp quyền OAuth thủ công cho tài khoản đó."""


class GmailFetchError(RuntimeError):
    """Gọi Gmail API thất bại (lỗi mạng, rate limit, quota, message không tồn tại...)."""


@dataclass(slots=True)
class GmailMessageSummary:
    """Metadata nhẹ — đủ để chạy lọc cổ điển (mục 3), CHƯA có nội dung đầy đủ. Chỉ email khớp bộ
    lọc mới cần fetch thêm qua `get_message_body()` — tránh tải nội dung đầy đủ cho MỌI email
    trong hộp thư, chỉ tải cho email thực sự nghi liên quan (đúng nguyên tắc riêng tư mục 2)."""

    message_id: str
    sender: str
    subject: str
    snippet: str
    received_at: datetime


class GmailClient:
    def __init__(self, *, account_email: str, token_path: Path) -> None:
        self.account_email = account_email
        self._token_path = token_path
        self._service: Any = None  # lazy build — lỗi auth raise đúng lúc dùng, không lúc khởi tạo

    def _load_credentials(self) -> Credentials:
        if not self._token_path.is_file():
            raise GmailAuthError(
                f"Chưa có token cho tài khoản {self.account_email} (thiếu file "
                f"{self._token_path}). Chạy lại luồng cấp quyền OAuth thủ công cho tài khoản này "
                "trước (xem điều kiện tiên quyết)."
            )

        try:
            creds = Credentials.from_authorized_user_file(
                str(self._token_path), [GMAIL_READONLY_SCOPE]
            )
        except (ValueError, OSError) as exc:
            raise GmailAuthError(
                f"File token của {self.account_email} không đọc được/sai định dạng: {exc}. "
                "Chạy lại luồng cấp quyền OAuth thủ công cho tài khoản này."
            ) from exc

        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as exc:  # lỗi mạng, refresh_token bị thu hồi...
                raise GmailAuthError(
                    f"Token của {self.account_email} hết hạn và refresh thất bại: {exc}. "
                    "KHÔNG tự đăng nhập lại bằng mật khẩu — chạy lại luồng cấp quyền OAuth thủ "
                    "công cho tài khoản này."
                ) from exc
            # Lưu lại access token mới để lần chạy sau không phải refresh lại từ đầu — đúng
            # pattern chính thức của Google (quickstart cũng ghi đè token.json sau khi refresh).
            self._token_path.write_text(creds.to_json(), encoding="utf-8")

        if not creds.valid:
            raise GmailAuthError(
                f"Token của {self.account_email} không hợp lệ và không refresh được (thiếu "
                "refresh_token, hoặc quyền đã bị thu hồi). Chạy lại luồng cấp quyền OAuth thủ "
                "công cho tài khoản này."
            )

        return creds

    def _get_service(self) -> Any:
        if self._service is None:
            creds = self._load_credentials()
            self._service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        return self._service

    def list_message_summaries_since(self, since: datetime) -> list[GmailMessageSummary]:
        """Metadata nhẹ (sender/subject/snippet/received_at) cho MỌI email nhận sau `since` —
        dùng Gmail search query `after:YYYY/MM/DD` để lọc phía server, không tải toàn bộ hộp thư
        về rồi lọc tay. CHƯA fetch body — xem docstring `GmailMessageSummary`.
        """
        service = self._get_service()
        query = f"after:{since.strftime('%Y/%m/%d')}"

        message_ids: list[str] = []
        page_token: str | None = None
        try:
            while True:
                response = (
                    service.users()
                    .messages()
                    .list(userId="me", q=query, pageToken=page_token)
                    .execute()
                )
                message_ids.extend(item["id"] for item in response.get("messages", []))
                page_token = response.get("nextPageToken")
                if not page_token:
                    break
        except HttpError as exc:
            raise GmailFetchError(
                f"Không lấy được danh sách email cho {self.account_email}: {exc}"
            ) from exc

        return [self._get_message_summary(message_id) for message_id in message_ids]

    def _get_message_summary(self, message_id: str) -> GmailMessageSummary:
        service = self._get_service()
        try:
            raw = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=message_id,
                    format="metadata",
                    metadataHeaders=["From", "Subject"],
                )
                .execute()
            )
        except HttpError as exc:
            raise GmailFetchError(
                f"Không lấy được metadata email {message_id} ({self.account_email}): {exc}"
            ) from exc

        headers = {h["name"].lower(): h["value"] for h in raw.get("payload", {}).get("headers", [])}
        return GmailMessageSummary(
            message_id=message_id,
            sender=headers.get("from", ""),
            subject=headers.get("subject", ""),
            snippet=raw.get("snippet", ""),
            received_at=datetime.fromtimestamp(int(raw["internalDate"]) / 1000, tz=timezone.utc),
        )

    def get_message_body(self, message_id: str) -> str:
        """Nội dung text CỦA ĐÚNG 1 MESSAGE này — gọi `messages().get()` theo `message_id` đơn
        lẻ, KHÔNG phải `threads().get()`, nên tự nhiên chỉ trả nội dung của message này, không
        phải cả thread trả lời qua lại (đúng nguyên tắc riêng tư mục 2: không gửi cả thread dài
        cho model). CHỈ gọi cho email đã khớp bộ lọc cổ điển — không gọi tràn lan cho mọi email.
        """
        service = self._get_service()
        try:
            raw = (
                service.users().messages().get(userId="me", id=message_id, format="full").execute()
            )
        except HttpError as exc:
            raise GmailFetchError(
                f"Không lấy được nội dung email {message_id} ({self.account_email}): {exc}"
            ) from exc

        return _extract_plain_text(raw.get("payload", {}))


def _extract_plain_text(payload: dict[str, Any]) -> str:
    """Ưu tiên `text/plain`; nếu chỉ có `text/html` thì strip tag thô (không cần thư viện HTML
    parser đầy đủ cho việc này — chỉ cần đủ sạch để LLM đọc được, không cần render đẹp)."""
    plain = _find_part(payload, "text/plain")
    if plain is not None:
        return plain
    html = _find_part(payload, "text/html")
    if html is not None:
        return re.sub(r"<[^>]+>", " ", html)
    return ""


def _find_part(payload: dict[str, Any], mime_type: str) -> str | None:
    if payload.get("mimeType") == mime_type:
        data = payload.get("body", {}).get("data")
        if data:
            padded = data + "=" * (-len(data) % 4)
            return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")
        return None
    for part in payload.get("parts", []) or []:
        found = _find_part(part, mime_type)
        if found is not None:
            return found
    return None
