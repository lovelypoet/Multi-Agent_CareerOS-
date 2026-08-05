"""Endpoint dashboard — 3 con số tổng quan, không biểu đồ."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_session
from app.repositories.dashboard_repository import DashboardRepository
from app.schemas.dashboard import DashboardSummary

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
async def dashboard_summary(session: AsyncSession = Depends(get_session)) -> DashboardSummary:
    settings = get_settings()
    return await DashboardRepository(session).get_summary(timezone=settings.dashboard_timezone)
