"""Cấu hình toàn app, đọc từ biến môi trường / file .env.

Không hardcode secret ở bất kỳ đâu khác trong codebase.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Thư mục chứa credentials.json/token_*.json — luôn là backend/, bất kể cwd lúc chạy process.
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Database -----------------------------------------------------------
    # Dùng driver asyncpg cho toàn bộ app (kể cả Alembic).
    database_url: str = "postgresql+asyncpg://careeros:careeros@localhost:5432/careeros"

    # --- LLM provider ---------------------------------------------------------
    # Chọn provider cho matching_agent qua .env, không sửa code. Mặc định vẫn Claude —
    # đổi hẳn sang local bằng LLM_PROVIDER=ollama, hoặc kiểm tra chéo 2 model local bằng
    # LLM_PROVIDER=ollama_ensemble (xem matching_agent.py).
    llm_provider: Literal["anthropic", "ollama", "ollama_ensemble"] = "anthropic"

    # --- Anthropic ----------------------------------------------------------
    anthropic_api_key: str = ""
    # Model đề xuất cho Phase 0 theo prompts/matching_v1.md.
    anthropic_model: str = "claude-sonnet-5"
    anthropic_max_tokens: int = 2000
    anthropic_timeout_seconds: float = 90.0

    # --- Ollama (local model) -------------------------------------------------
    ollama_model: str = "qwen2.5:7b"
    ollama_host: str = "http://localhost:11434"
    # Model thứ 2 dùng cho ollama_ensemble — kiến trúc khác hẳn qwen2.5 để kiểm tra chéo
    # có ý nghĩa (2 model cùng họ dễ mắc chung lỗi, không phát hiện được gì).
    ollama_secondary_model: str = "llama3.1:8b"

    # --- App ----------------------------------------------------------------
    cors_origins: str = "http://localhost:3000"
    # Phase 0: chỉ 1 resume duy nhất, luôn nằm ở id cố định này.
    resume_singleton_id: int = 1

    # --- Phase 1: fetch job tự động ------------------------------------------
    # Giờ chạy hàng ngày (giờ server), mặc định 8:00 sáng, override qua env nếu cần.
    fetch_jobs_hour: int = 8
    fetch_jobs_minute: int = 0

    # --- Phase 2: dashboard ---------------------------------------------------
    # "jobs_today" tính theo múi giờ này, không theo UTC của server.
    dashboard_timezone: str = "Asia/Ho_Chi_Minh"

    # --- Phase 3 việc #4: pgvector — lọc rẻ + tìm kiếm theo ý nghĩa --------------------------
    # Bản đa ngôn ngữ — bản gốc `nomic-embed-text` tối ưu chủ yếu tiếng Anh, không hợp vì nội
    # dung dự án chủ yếu tiếng Việt. Dimension thật (768) đã tự verify qua `ollama.embed()`,
    # không đoán từ tài liệu — xem `integrations/embedding_client.py`.
    embedding_model: str = "nomic-embed-text-v2-moe"
    # Ngưỡng bắt đầu — tự tính từ 2 mốc đo thật lúc verify chất lượng model với câu tiếng Việt
    # (similarity 2 câu gần nghĩa ~0.43, 2 câu không liên quan ~0.07; lấy điểm giữa). Vẫn CẦN
    # tinh chỉnh thêm sau khi quan sát kết quả lọc thật, không phải con số cuối cùng.
    embedding_similarity_threshold: float = 0.25

    # --- Phase 3 việc #1: Gmail monitoring (giai đoạn 1 — chỉ đọc & phân loại) --------------
    # Danh sách email, cách nhau bởi dấu phẩy — vd "ducanh3105.work@gmail.com,other@gmail.com".
    # Rỗng = chưa cấu hình tài khoản nào, worker tự bỏ qua, không lỗi (xem workers/fetch_emails.py).
    gmail_account_emails: str = ""
    # Lần quét ĐẦU TIÊN cho 1 tài khoản (chưa từng có email_notifications nào) lùi lại bao
    # nhiêu ngày — KHÔNG quét toàn bộ lịch sử hộp thư. Các lần sau dùng received_at mới nhất
    # của chính tài khoản đó, không dùng số này nữa.
    gmail_initial_lookback_days: int = 7
    # Tần suất quét — vài lần/ngày, không cần gấp bằng việc fetch job (Phase 1 chỉ 1 lần/ngày).
    gmail_fetch_interval_hours: int = 6

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def gmail_account_email_list(self) -> list[str]:
        return [email.strip() for email in self.gmail_account_emails.split(",") if email.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


def token_path_for(account_email: str) -> Path:
    """Suy ra đường dẫn file token OAuth từ chính email tài khoản — không cấu hình riêng từng
    đường dẫn, không cần bảng ánh xạ. Thay `@` bằng `_`, GIỮ NGUYÊN cả phần domain (nhiều dấu
    chấm trong tên file là bình thường trên hầu hết filesystem) — an toàn hơn nếu sau này có 2
    tài khoản trùng phần trước `@` nhưng khác domain.

    Ví dụ: "ducanh3105.work@gmail.com" -> "backend/token_ducanh3105.work_gmail.com.json"
    """
    filename = "token_" + account_email.replace("@", "_") + ".json"
    return BACKEND_DIR / filename


def credentials_path() -> Path:
    """OAuth Client ID (loại Desktop app) — DÙNG CHUNG cho mọi tài khoản Gmail theo dõi, khác
    với token (mỗi tài khoản 1 file riêng, xem `token_path_for`). Tự tạo thủ công theo điều
    kiện tiên quyết ở đầu prompt, KHÔNG commit (xem .gitignore)."""
    return BACKEND_DIR / "credentials.json"
