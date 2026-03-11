from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from src.database.models import Opportunity, RawSignal, ScanLog, get_session

logger = logging.getLogger(__name__)

router = APIRouter()

FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend"
INDEX_HTML = FRONTEND_DIR / "index.html"


@router.get("/", include_in_schema=False)
async def serve_frontend():
    if INDEX_HTML.exists():
        return FileResponse(str(INDEX_HTML))
    return JSONResponse(
        {
            "name": "Fikir Bulucu - AI Opportunity Radar",
            "version": "1.0.0",
            "status": "running",
            "endpoints": [
                "/api/opportunities/today",
                "/api/opportunities/history",
                "/api/opportunities/{date}",
                "/api/signals/today",
                "/api/scan/status",
                "/api/scan/trigger",
            ],
        }
    )


@router.get("/api/opportunities/today")
async def get_today_opportunities() -> dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    with get_session() as session:
        opportunities = (
            session.query(Opportunity)
            .filter(Opportunity.created_date == today)
            .order_by(Opportunity.score.desc())
            .all()
        )

        # If no opportunities today, return most recent available data
        actual_date = today
        if not opportunities:
            opportunities = (
                session.query(Opportunity)
                .order_by(Opportunity.created_date.desc(), Opportunity.score.desc())
                .limit(20)
                .all()
            )
            if opportunities:
                actual_date = opportunities[0].created_date

        return {
            "date": actual_date.isoformat() if actual_date else today.isoformat(),
            "count": len(opportunities),
            "opportunities": [opp.to_dict() for opp in opportunities],
        }


@router.get("/api/opportunities/history")
async def get_opportunities_history() -> dict[str, Any]:
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=30)
    with get_session() as session:
        opportunities = (
            session.query(Opportunity)
            .filter(Opportunity.created_date >= cutoff)
            .order_by(Opportunity.created_date.desc(), Opportunity.score.desc())
            .all()
        )

        by_date: dict[str, list[dict]] = {}
        for opp in opportunities:
            d = opp.created_date.isoformat() if opp.created_date else "unknown"
            by_date.setdefault(d, []).append(opp.to_dict())

        return {
            "from_date": cutoff.isoformat(),
            "to_date": datetime.now(timezone.utc).date().isoformat(),
            "total_count": len(opportunities),
            "by_date": by_date,
        }


@router.get("/api/opportunities/week-best")
async def get_week_best() -> dict[str, Any]:
    """Return the highest-scored opportunity from the last 7 days"""
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=7)
    with get_session() as session:
        opp = (
            session.query(Opportunity)
            .filter(Opportunity.created_date >= cutoff)
            .order_by(Opportunity.score.desc())
            .first()
        )
        return {"opportunity": opp.to_dict() if opp else None}

@router.get("/api/opportunities/month-best")
async def get_month_best() -> dict[str, Any]:
    """Return the highest-scored opportunity from the last 30 days"""
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=30)
    with get_session() as session:
        opp = (
            session.query(Opportunity)
            .filter(Opportunity.created_date >= cutoff)
            .order_by(Opportunity.score.desc())
            .first()
        )
        return {"opportunity": opp.to_dict() if opp else None}

@router.get("/api/opportunities/{scan_date}")
async def get_opportunities_by_date(scan_date: str) -> dict[str, Any]:
    try:
        target_date = date.fromisoformat(scan_date)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {scan_date}. Use YYYY-MM-DD.")

    with get_session() as session:
        opportunities = (
            session.query(Opportunity)
            .filter(Opportunity.created_date == target_date)
            .order_by(Opportunity.score.desc())
            .all()
        )
        return {
            "date": target_date.isoformat(),
            "count": len(opportunities),
            "opportunities": [opp.to_dict() for opp in opportunities],
        }


@router.get("/api/signals/today")
async def get_today_signals() -> dict[str, Any]:
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    with get_session() as session:
        signals = (
            session.query(RawSignal)
            .filter(RawSignal.scraped_at >= today_start)
            .all()
        )

        by_source: dict[str, int] = {}
        for signal in signals:
            by_source[signal.source] = by_source.get(signal.source, 0) + 1

        return {
            "date": today_start.date().isoformat(),
            "total": len(signals),
            "by_source": by_source,
        }


@router.get("/api/scan/status")
async def get_scan_status() -> dict[str, Any]:
    with get_session() as session:
        latest_logs = (
            session.query(ScanLog)
            .order_by(ScanLog.started_at.desc())
            .limit(20)
            .all()
        )

        if not latest_logs:
            return {"status": "never_run", "last_scan": None, "sources": []}

        last_started = latest_logs[0].started_at if latest_logs else None
        any_errors = any(log.status == "error" for log in latest_logs[:6])

        return {
            "status": "error" if any_errors else "ok",
            "last_scan": last_started.isoformat() if last_started else None,
            "sources": [log.to_dict() for log in latest_logs],
        }


def _background_scan() -> None:
    try:
        from src.scanner import run_daily_scan
        result = run_daily_scan()
        logger.info("Background scan completed: %s", result)
    except Exception as exc:
        logger.error("Background scan failed: %s", exc, exc_info=True)


@router.post("/api/scan/trigger")
async def trigger_scan(background_tasks: BackgroundTasks) -> dict[str, Any]:
    background_tasks.add_task(_background_scan)
    return {
        "status": "triggered",
        "message": "Scan started in background. Check /api/scan/status for progress.",
        "triggered_at": datetime.now(timezone.utc).isoformat(),
    }
