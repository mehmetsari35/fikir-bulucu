from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.database.models import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
DATA_DIR = BASE_DIR / "data"

_scheduler = None


def _start_scheduler() -> None:
    global _scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger

        from src.config import settings
        from src.scanner import run_daily_scan

        _scheduler = BackgroundScheduler(timezone="UTC")
        _scheduler.add_job(
            run_daily_scan,
            trigger=IntervalTrigger(hours=settings.SCAN_INTERVAL_HOURS),
            id="daily_scan",
            name="Daily opportunity scan",
            replace_existing=True,
        )
        _scheduler.start()
        logger.info(
            "APScheduler started. Scan interval: %d hours", settings.SCAN_INTERVAL_HOURS
        )
    except ImportError:
        logger.warning("APScheduler not installed; scheduled scans disabled")
    except Exception as exc:
        logger.error("Failed to start scheduler: %s", exc)


def _stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
            logger.info("APScheduler stopped")
        except Exception as exc:
            logger.warning("Error stopping scheduler: %s", exc)
        _scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized")

    _start_scheduler()

    yield

    _stop_scheduler()
    logger.info("Fikir Bulucu shutdown complete")


app = FastAPI(
    title="Fikir Bulucu - AI Opportunity Radar",
    description="Personal intelligence tool for discovering business opportunities from real-time signals",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from src.api.routes import router  # noqa: E402
app.include_router(router)

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
    logger.info("Static files mounted from %s", FRONTEND_DIR)
