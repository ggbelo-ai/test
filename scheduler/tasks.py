"""Celery tasks — wrappers around agent entry points."""

from __future__ import annotations

import logging

from scheduler.celery_app import app

logger = logging.getLogger(__name__)


@app.task(name="scheduler.tasks.run_horizon_scanner")
def run_horizon_scanner() -> dict:
    """Daily task: run the Horizon Scanner and route novel themes to Orchestrator."""
    from agents.horizon_scanner import scan_horizon
    from agents.orchestrator import route_task

    logger.info("Celery: starting Horizon Scanner")
    themes = scan_horizon()

    for theme in themes:
        route_task("new_theme", {
            "id": None,  # Will be set after DB insert in scan_horizon
            "label": theme.label,
            "novelty_score": theme.novelty_score,
            "signal_maturity": theme.signal_maturity,
            "signal_sources": theme.signal_sources,
            "description": theme.description,
        })

    return {"themes_discovered": len(themes)}


@app.task(name="scheduler.tasks.run_founder_radar")
def run_founder_radar() -> dict:
    """Weekly task: scan for high-signal founders and route alerts to Orchestrator."""
    from agents.founder_radar import SIGNAL_SCORE_THRESHOLD, scan_founder
    from agents.orchestrator import route_task

    logger.info("Celery: starting Founder Radar")

    # In production, this would iterate over tracked individuals
    # from Twitter/X lists, GitHub watchlists, etc.
    # For now, this is a placeholder structure.
    high_signal_count = 0

    # Example: would be populated by monitoring pipelines
    tracked_profiles: list[dict] = []

    for profile in tracked_profiles:
        result = scan_founder(
            name=profile["name"],
            signals=profile.get("signals", []),
            theme_id=profile.get("theme_id"),
            twitter_handle=profile.get("twitter_handle"),
            github_username=profile.get("github_username"),
        )

        if result.signal_score >= SIGNAL_SCORE_THRESHOLD:
            route_task("founder_alert", {
                "name": result.name,
                "signal_score": result.signal_score,
                "signals_detected": result.signals_detected,
                "likely_theme_id": result.likely_theme_id,
                "recommended_action": result.recommended_action,
                "draft_outreach": result.draft_outreach,
            })
            high_signal_count += 1

    return {"profiles_scanned": len(tracked_profiles), "high_signal": high_signal_count}
