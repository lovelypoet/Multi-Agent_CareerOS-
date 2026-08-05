"""CareerOS backend — MỘT process FastAPI duy nhất.

API, repositories và AI agent đều chạy trong process này. Agent là Python package được import
trực tiếp, không phải service riêng, không có port/Dockerfile riêng.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.workers.fetch_jobs import run_fetch_jobs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # APScheduler chạy trong CÙNG process backend (không Redis Queue) — hợp lý cho Phase 1
    # với 1 process uvicorn duy nhất. LƯU Ý CHO TƯƠNG LAI: nếu sau này chạy uvicorn với
    # nhiều worker (--workers N), lịch này sẽ khởi tạo N lần và chạy job trùng lặp N lần.
    # Phase 1 mặc định 1 process nên chưa phải vấn đề, nhưng cần Redis lock hoặc job
    # nằm ngoài process backend nếu scale sau này.
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_fetch_jobs,
        trigger=CronTrigger(hour=settings.fetch_jobs_hour, minute=settings.fetch_jobs_minute),
        id="fetch_jobs_daily",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "[scheduler] fetch_jobs lên lịch chạy hàng ngày lúc %02d:%02d",
        settings.fetch_jobs_hour,
        settings.fetch_jobs_minute,
    )
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="CareerOS API",
    version="0.1.0",
    description="Phase 0 — dán job description, chấm điểm match với CV, xem lại lịch sử.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
