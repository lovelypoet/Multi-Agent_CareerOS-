"""Cấu hình toàn app, đọc từ biến môi trường / file .env.

Không hardcode secret ở bất kỳ đâu khác trong codebase.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
