"""Cấu hình lọc email liên quan tuyển dụng — KHÔNG phải logic AI, chỉ là danh sách + 1 hàm so
khớp thuần. Người dùng chỉnh sửa `GENERIC_KEYWORDS` trực tiếp để thêm/bớt từ khóa, không cần đụng
vào `email_classifier_agent` hay `workers/fetch_emails.py`. Đây là bước lọc cổ điển (classical
filter) chạy TRƯỚC khi tốn 1 lệnh gọi AI — chỉ email nào khớp mới được gửi nội dung qua LLM.

Danh sách KHỞI ĐIỂM, cần tự tinh chỉnh sau khi dùng thật một thời gian và quan sát tỷ lệ nhiễu —
giống cách `relevance_keywords.py` (Phase 1) đã được thiết kế để chỉnh sửa dần, không phải danh
sách cố định đúng ngay từ đầu.

Đã cố tình BỎ 2 từ khóa nghĩ tới ban đầu:
- "offer": từ khóa marketing/khuyến mãi cực phổ biến ("special offer", "limited offer") — sẽ
  kéo nhiều email quảng cáo không liên quan qua LLM, phản tác dụng chính mục đích giảm nhiễu.
- "unfortunately"/"rất tiếc": quá chung chung, xuất hiện trong vô số ngữ cảnh không liên quan
  tuyển dụng (delay chuyến bay, hết hàng...).
Giữ lại "cảm ơn bạn đã quan tâm" vì đây là cụm khá đặc trưng cho email từ chối tuyển dụng tiếng
Việt ("Cảm ơn bạn đã quan tâm đến vị trí..."), không chung chung như 2 cụm bị bỏ. Nếu sau này
nhận thấy bộ lọc hiện tại bỏ sót email từ chối/mời phỏng vấn thật, cân nhắc thêm lại có kiểm soát
(ví dụ chỉ thêm nếu đi kèm điều kiện khác), không thêm tràn lan lại.
"""

from __future__ import annotations

GENERIC_KEYWORDS = [
    "phỏng vấn",
    "interview",
    "ứng tuyển",
    "ứng viên",
    "cảm ơn bạn đã quan tâm",
    "trúng tuyển",
    "vị trí ứng tuyển",
    "kết quả ứng tuyển",
]


def company_names_match(a: str, b: str) -> bool:
    """So khớp lỏng, case-insensitive, substring 2 CHIỀU — DÙNG CHUNG cho CẢ lọc cổ điển (khớp
    `jobs.company` với sender/subject/snippet) LẪN đối chiếu tìm `job_id` từ
    `company_name_mentioned` model trích xuất — 1 nguồn logic duy nhất đảm bảo nhất quán bằng
    thiết kế, thay vì viết 2 lần dễ lệch nhau (bug loại này đã từng xảy ra thật ở chỗ khác trong
    dự án, xem `job_repository.py`).

    2 chiều vì độ dài 2 chuỗi có thể lệch nhau theo cả 2 hướng tuỳ ngữ cảnh: `jobs.company` có
    thể dài hơn (vd DB lưu "Công ty TNHH ABC" nhưng email/tiêu đề chỉ ghi "ABC") hoặc ngắn hơn
    (vd DB lưu "ABC" nhưng model trích xuất "Công ty TNHH ABC Việt Nam" từ chữ ký email) —
    substring 1 chiều sẽ bỏ sót 1 trong 2 tình huống này.
    """
    a_norm, b_norm = a.strip().lower(), b.strip().lower()
    if not a_norm or not b_norm:
        return False
    return a_norm in b_norm or b_norm in a_norm
