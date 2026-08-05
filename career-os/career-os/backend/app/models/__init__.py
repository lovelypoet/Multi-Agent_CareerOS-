"""Nơi DUY NHẤT định nghĩa schema DB (không có folder database/ riêng).

Import tất cả model ở đây để Alembic autogenerate nhìn thấy đủ bảng qua `Base.metadata`.
"""

from app.models.agent_run import AgentRun
from app.models.application import Application
from app.models.base import Base
from app.models.job import Job
from app.models.match_result import MatchResult
from app.models.resume import Resume

__all__ = ["Base", "Job", "Resume", "MatchResult", "AgentRun", "Application"]
