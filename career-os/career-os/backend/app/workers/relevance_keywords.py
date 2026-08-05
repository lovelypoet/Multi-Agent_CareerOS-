"""Cấu hình từ khóa lọc job liên quan — KHÔNG phải logic AI, chỉ là danh sách.

Người dùng chỉnh sửa file này trực tiếp để thêm/bớt từ khóa, không cần đụng vào
matching_agent hay bất kỳ logic AI nào. Đây là bước lọc cổ điển (classical filter)
chạy TRƯỚC khi tốn 1 lệnh gọi AI — chỉ job nào khớp mới được fetch full description
và đưa qua matching_agent.
"""

RELEVANT_KEYWORDS = [
    # Data Engineering
    "data engineering", "data engineer", "etl", "data pipeline",
    # AI Engineering
    "ai engineer", "artificial intelligence",
    # Machine Learning
    "machine learning", "ml engineer", "deep learning", "robot learning",
    # Computer Vision / Machine Vision
    "computer vision", "machine vision",
    # Robotics
    "robotics", "robot", "ros", "ros2",
    # Embedded / Robot software
    "embedded", "embedded software", "robot embedded", "firmware",
    "real-time systems", "iot", "nhúng",
]

# Level filter: cả Fresher và Junior đều giữ lại (theo quyết định của user).
# Đây là tín hiệu TÍCH CỰC để kiểm tra trong title/description — KHÔNG phải 1 field
# riêng biệt trên listing page (ITviec không hiển thị field đó). Xem prompt Phase 1
# mục 3 để biết logic đầy đủ: nếu không tìm thấy tín hiệu nào (cả tích cực lẫn dưới
# đây) thì GIỮ job đó, không loại.
RELEVANT_LEVELS = ["internship", "fresher", "junior", "thực tập", "mới tốt nghiệp"]

# Tín hiệu LOẠI — xuất hiện rõ ràng trong title/description thì loại job đó.
SENIOR_SIGNALS = [
    "senior", "5+ years", "5+ năm", "3+ years", "3+ năm",
    "trưởng nhóm", "manager", "lead ",
]
