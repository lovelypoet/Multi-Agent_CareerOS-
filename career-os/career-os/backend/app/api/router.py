"""Gom toàn bộ router của API."""

from fastapi import APIRouter

from app.api import applications, dashboard, jobs, resume

api_router = APIRouter()
api_router.include_router(jobs.router)
api_router.include_router(resume.router)
api_router.include_router(applications.router)
api_router.include_router(dashboard.router)
