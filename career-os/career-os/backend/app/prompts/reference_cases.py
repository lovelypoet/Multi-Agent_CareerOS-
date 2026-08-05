"""Test case tham khảo để kiểm tra chất lượng output của `matching_agent` qua các provider
khác nhau — dữ liệu dùng bởi `scripts/compare_providers.py`.

KHÔNG phải nội dung prompt gửi cho model — tách khỏi `prompts/matching_v1.md` để file đó
giữ nguyên, tập trung đúng vào prompt. Case "good_match" gốc lấy đúng theo mô tả ở cuối
`matching_v1.md`; 3 case A/B/C thêm ở đây để phủ đủ các dải điểm còn thiếu
(strong/weak/partial) — case gốc chỉ kiểm tra được dải good_match.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ReferenceCase:
    label: str
    resume_text: str
    job_description_text: str
    expected_score_range: tuple[int, int]
    expected_verdict: str


GOOD_MATCH = ReferenceCase(
    label="good_match (gốc, matching_v1.md)",
    resume_text="""Nguyễn Văn A — Frontend Developer

Kinh nghiệm làm việc (3 năm):
- Phát triển và bảo trì các ứng dụng web sử dụng ReactJS tại công ty ABC Tech (2023-nay).
- Xây dựng component tái sử dụng, quản lý state với Redux, làm việc với REST API.
- Có kiến thức cơ bản về TypeScript, từng viết một số phần nhỏ của dự án bằng TypeScript,
  phần lớn công việc hàng ngày vẫn dùng JavaScript thuần.
- Chưa có kinh nghiệm thực tế với Python.
- Chưa từng triển khai ứng dụng lên AWS, chỉ mới đọc tài liệu cơ bản.

Kỹ năng: ReactJS, Redux, JavaScript (ES6+), TypeScript (cơ bản), HTML5, CSS3, Git.

Học vấn: Cử nhân Công nghệ thông tin.""",
    job_description_text="""Tuyển dụng: Frontend Developer

Yêu cầu bắt buộc (must-have):
- Tối thiểu 3 năm kinh nghiệm làm việc với ReactJS.
- Thành thạo TypeScript trong dự án thực tế.

Ưu tiên (nice-to-have):
- Có kinh nghiệm với Python (viết script tự động hoá hoặc backend đơn giản).
- Có kinh nghiệm triển khai ứng dụng lên AWS.

Mô tả công việc: Tham gia phát triển sản phẩm web, phối hợp với team backend và design,
đảm bảo chất lượng code và hiệu năng ứng dụng.""",
    expected_score_range=(65, 80),
    expected_verdict="good_match",
)

STRONG_MATCH = ReferenceCase(
    label="strong_match (Case A)",
    resume_text="""Trần Thị B — Senior Frontend Developer

Kinh nghiệm làm việc (4 năm):
- 4 năm phát triển ứng dụng web với ReactJS, trong đó 2 năm gần nhất sử dụng TypeScript
  cho toàn bộ codebase tại công ty DEF Solutions.
- Thiết kế kiến trúc component, tối ưu hiệu năng render, viết unit test với Jest/RTL.
- Từng triển khai 1 dự án lên AWS (S3 + CloudFront cho static hosting, có dùng Lambda
  cho vài API đơn giản).
- Thành thạo Git, CI/CD cơ bản.

Kỹ năng: ReactJS, TypeScript, Redux, AWS (S3, CloudFront, Lambda), Jest, HTML5, CSS3.

Học vấn: Cử nhân Công nghệ thông tin.""",
    job_description_text="""Tuyển dụng: Senior Frontend Developer

Yêu cầu bắt buộc (must-have):
- Tối thiểu 2 năm kinh nghiệm làm việc với ReactJS.
- Thành thạo TypeScript trong dự án thực tế.

Ưu tiên (nice-to-have):
- Có kinh nghiệm triển khai ứng dụng lên AWS.
- Có kinh nghiệm sử dụng Docker.

Mô tả công việc: Dẫn dắt kỹ thuật cho các dự án frontend quy mô vừa, phối hợp chặt chẽ
với team DevOps để tối ưu quy trình triển khai.""",
    expected_score_range=(85, 100),
    expected_verdict="strong_match",
)

WEAK_MATCH = ReferenceCase(
    label="weak_match (Case B)",
    resume_text="""Lê Văn C — Mobile Developer

Kinh nghiệm làm việc (5 năm):
- 5 năm phát triển ứng dụng di động native cho iOS (Swift) và Android (Kotlin) tại
  công ty GHI Mobile.
- Xây dựng và duy trì nhiều ứng dụng thương mại điện tử trên cả 2 nền tảng, tích hợp
  push notification, in-app purchase, offline sync.
- Chưa từng làm việc với ReactJS hoặc bất kỳ framework web frontend nào.
- Không có kinh nghiệm với TypeScript hay Redux.

Kỹ năng: Swift, SwiftUI, Kotlin, Jetpack Compose, Firebase, REST API.

Học vấn: Cử nhân Kỹ thuật phần mềm.""",
    job_description_text="""Tuyển dụng: Frontend Developer (React)

Yêu cầu bắt buộc (must-have):
- Tối thiểu 3 năm kinh nghiệm làm việc với ReactJS.
- Thành thạo TypeScript trong dự án thực tế.
- Có kinh nghiệm quản lý state với Redux.

Mô tả công việc: Phát triển và bảo trì hệ thống frontend cho sản phẩm SaaS B2B, làm
việc trực tiếp với team backend Node.js.""",
    expected_score_range=(0, 39),
    expected_verdict="weak_match",
)

PARTIAL_MATCH = ReferenceCase(
    label="partial_match (Case C)",
    resume_text="""Phạm Thị D — Frontend Developer

Kinh nghiệm làm việc (1 năm chuyên React, trước đó 3 năm ở vị trí Backend Engineer):
- 1 năm gần nhất chuyển sang làm Frontend, phát triển ứng dụng với ReactJS tại công ty
  JKL Startup.
- Trước đó có 3 năm kinh nghiệm làm Backend Engineer, trong đó tham gia thiết kế kiến
  trúc hệ thống phân tán (system design) cho sản phẩm quy mô lớn, xử lý hàng triệu
  request/ngày.
- Sử dụng TypeScript thành thạo cho cả phần backend (NestJS) lẫn phần frontend React
  hiện tại — viết type-safe code, tự định nghĩa generic types phức tạp.
- Tự tin trình bày và phản biện các quyết định về kiến trúc hệ thống.

Kỹ năng: ReactJS (1 năm), TypeScript (thành thạo, 4 năm), System Design, Node.js,
NestJS, PostgreSQL, Docker.

Học vấn: Cử nhân Khoa học máy tính.""",
    job_description_text="""Tuyển dụng: Frontend Developer

Yêu cầu bắt buộc (must-have):
- Tối thiểu 3 năm kinh nghiệm làm việc với ReactJS.

Ưu tiên (nice-to-have):
- Thành thạo TypeScript.
- Có tư duy/kinh nghiệm về system design.

Mô tả công việc: Phát triển tính năng mới cho sản phẩm web, tham gia thảo luận kiến
trúc kỹ thuật cùng team.""",
    expected_score_range=(40, 64),
    expected_verdict="partial_match",
)

ALL_CASES: list[ReferenceCase] = [GOOD_MATCH, STRONG_MATCH, WEAK_MATCH, PARTIAL_MATCH]
