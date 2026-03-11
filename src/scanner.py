from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.database.models import Opportunity, RawSignal, ScanLog, get_session
from src.scrapers import ALL_SCRAPERS

logger = logging.getLogger(__name__)


def _run_scraper(scraper_class) -> tuple[str, list[dict], str | None]:
    scraper = scraper_class()
    try:
        signals = scraper.scrape()
        return scraper.name, signals, None
    except Exception as exc:
        logger.error("Scraper %s crashed: %s", scraper_class.__name__, exc, exc_info=True)
        return scraper_class.name if hasattr(scraper_class, "name") else scraper_class.__name__, [], str(exc)


def _store_raw_signals(scraper_name: str, signals: list[dict]) -> list[int]:
    stored_ids: list[int] = []
    if not signals:
        return stored_ids

    with get_session() as session:
        for signal in signals:
            raw = RawSignal(
                source=scraper_name,
                title=signal.get("title", "")[:500],
                url=(signal.get("url") or "")[:1000],
                content=signal.get("content") or "",
                processed=False,
            )
            raw.metadata_dict = signal.get("metadata") or {}
            session.add(raw)
            session.flush()
            stored_ids.append(raw.id)

    return stored_ids


def _store_scan_log(
    source: str,
    status: str,
    signals_found: int,
    started_at: datetime,
    error_message: str | None = None,
) -> None:
    with get_session() as session:
        log = ScanLog(
            source=source,
            status=status,
            signals_found=signals_found,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            error_message=error_message,
        )
        session.add(log)


def _store_opportunity(opp: dict, signal_ids: list[int]) -> None:
    category_score_map = {
        "BEST": 0.95,
        "MEDIUM": 0.70,
        "SMALL": 0.50,
        "AI_SYNTHESIZED": 0.85,
    }
    category = opp.get("category", "MEDIUM")
    base_score = category_score_map.get(category, 0.60)

    difficulty = opp.get("difficulty", 3)
    difficulty_bonus = (5 - difficulty) * 0.02

    score = round(min(1.0, base_score + difficulty_bonus), 4)

    with get_session() as session:
        opportunity = Opportunity(
            title=opp.get("title", "")[:500],
            explanation=opp.get("explanation", ""),
            why_it_works=opp.get("why_it_works", ""),
            market_opportunity=opp.get("market_opportunity", ""),
            monetization=opp.get("monetization", ""),
            difficulty=opp.get("difficulty", 3),
            success_factors=opp.get("success_factors", ""),
            category=category,
            score=score,
        )
        opportunity.source_signals = signal_ids[:50]
        session.add(opportunity)


def _mark_signals_processed(signal_ids: list[int]) -> None:
    if not signal_ids:
        return
    with get_session() as session:
        session.query(RawSignal).filter(RawSignal.id.in_(signal_ids)).update(
            {"processed": True}, synchronize_session="fetch"
        )


def run_daily_scan() -> dict:
    scan_start = datetime.now(timezone.utc)
    logger.info("Starting daily scan at %s", scan_start.isoformat())

    all_signals: list[dict] = []
    all_signal_ids: list[int] = []
    scraper_results: list[dict] = []

    for scraper_class in ALL_SCRAPERS:
        started_at = datetime.now(timezone.utc)
        scraper_name, signals, error = _run_scraper(scraper_class)

        status = "error" if error else "success"
        signal_ids = []

        if signals:
            try:
                signal_ids = _store_raw_signals(scraper_name, signals)
                enriched = [dict(s, source=scraper_name) for s in signals]
                all_signals.extend(enriched)
                all_signal_ids.extend(signal_ids)
                logger.info("Stored %d signals from %s", len(signal_ids), scraper_name)
            except Exception as exc:
                logger.error("Failed to store signals from %s: %s", scraper_name, exc)
                status = "storage_error"
                error = str(exc)

        try:
            _store_scan_log(scraper_name, status, len(signal_ids), started_at, error)
        except Exception as exc:
            logger.error("Failed to store scan log for %s: %s", scraper_name, exc)

        scraper_results.append(
            {
                "source": scraper_name,
                "status": status,
                "signals_found": len(signal_ids),
                "error": error,
            }
        )

    logger.info("Total signals collected: %d", len(all_signals))

    opportunities: list[dict] = []
    analysis_error: str | None = None

    if all_signals:
        try:
            from src.analyzer.opportunity_analyzer import OpportunityAnalyzer

            analyzer = OpportunityAnalyzer()
            opportunities = analyzer.analyze_signals(all_signals)
            logger.info("Analyzer produced %d opportunities", len(opportunities))
        except ValueError as exc:
            analysis_error = str(exc)
            logger.error("Analyzer configuration error: %s", exc)
        except Exception as exc:
            analysis_error = str(exc)
            logger.error("Analyzer failed: %s", exc, exc_info=True)

    stored_count = 0
    for opp in opportunities:
        try:
            _store_opportunity(opp, all_signal_ids)
            stored_count += 1
        except Exception as exc:
            logger.error("Failed to store opportunity '%s': %s", opp.get("title", "?"), exc)

    if all_signal_ids:
        try:
            _mark_signals_processed(all_signal_ids)
        except Exception as exc:
            logger.error("Failed to mark signals as processed: %s", exc)

    scan_end = datetime.now(timezone.utc)
    duration_seconds = (scan_end - scan_start).total_seconds()

    result = {
        "started_at": scan_start.isoformat(),
        "completed_at": scan_end.isoformat(),
        "duration_seconds": round(duration_seconds, 2),
        "total_signals": len(all_signals),
        "opportunities_generated": stored_count,
        "scrapers": scraper_results,
        "analysis_error": analysis_error,
    }

    logger.info(
        "Daily scan complete. Duration: %.1fs, Signals: %d, Opportunities: %d",
        duration_seconds,
        len(all_signals),
        stored_count,
    )
    return result
