"""CareerOS API process: HTTP routes and lightweight scheduling only."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.services.scheduling import enqueue_fetch_emails, enqueue_fetch_jobs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The scheduler only enqueues idempotent PostgreSQL tasks. Crawling, embeddings, and AI
    # work run in the separately started `python -m app.worker` process.
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        enqueue_fetch_jobs,
        trigger=CronTrigger(hour=settings.fetch_jobs_hour, minute=settings.fetch_jobs_minute),
        id="fetch_jobs_daily",
        replace_existing=True,
    )
    # Phase 3 việc #1: quét Gmail vài lần/ngày — khác fetch_jobs (1 lần/ngày là đủ), vì biết có
    # ai mời phỏng vấn/từ chối gấp gáp hơn hẳn việc fetch job mới không quá khẩn.
    scheduler.add_job(
        enqueue_fetch_emails,
        trigger=IntervalTrigger(hours=settings.gmail_fetch_interval_hours),
        id="fetch_emails_periodic",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "[scheduler] fetch_jobs lên lịch chạy hàng ngày lúc %02d:%02d",
        settings.fetch_jobs_hour,
        settings.fetch_jobs_minute,
    )
    logger.info(
        "[scheduler] fetch_emails lên lịch chạy mỗi %d giờ",
        settings.gmail_fetch_interval_hours,
    )
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="CareerOS API",
    version="0.1.0",
    description="CareerOS API for job discovery, resume analysis, matching, and application tracking.",
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
