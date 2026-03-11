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
            "id": None,
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

    # Build tracked profiles from multiple data sources
    tracked_profiles = _gather_tracked_profiles()

    high_signal_count = 0
    for profile in tracked_profiles:
        result = scan_founder(
            name=profile["name"],
            signals=profile.get("signals", []),
            theme_id=profile.get("theme_id"),
            twitter_handle=profile.get("twitter_handle"),
            github_username=profile.get("github_username"),
            linkedin_url=profile.get("linkedin_url"),
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


def _gather_tracked_profiles() -> list[dict]:
    """Gather founder profiles to scan from multiple data sources.

    Combines:
    1. Existing founders in the knowledge graph that need re-scoring
    2. GitHub contributors to trending repos in active themes
    3. Semantic Scholar researchers in relevant fields

    Returns:
        List of profile dicts ready for scan_founder().
    """
    profiles: list[dict] = []
    seen_names: set[str] = set()

    # 1. Pull existing founders from knowledge graph that need re-scoring
    try:
        from db.supabase_client import list_founders
        existing_founders = list_founders(limit=100)
        for f in existing_founders:
            if f.get("partner_decision") != "pass":
                profiles.append({
                    "name": f["name"],
                    "signals": f.get("signals_detected", []),
                    "twitter_handle": f.get("twitter_handle"),
                    "github_username": f.get("github_username"),
                    "linkedin_url": f.get("linkedin_url"),
                })
                seen_names.add(f["name"])
    except Exception as exc:
        logger.warning("Failed to load existing founders: %s", exc)

    # 2. Discover new profiles from GitHub trending repos
    try:
        from integrations.github import fetch_github_trending
        trending = fetch_github_trending(stars_growth_pct_min=50, max_results=20)

        for repo in trending:
            owner = repo.repo_full_name.split("/")[0]
            if owner not in seen_names:
                profiles.append({
                    "name": owner,
                    "signals": ["open_source_repo_created"],
                    "github_username": owner,
                })
                seen_names.add(owner)
    except Exception as exc:
        logger.warning("Failed to gather GitHub profiles: %s", exc)

    # 3. Scan Semantic Scholar for researchers in active theme areas
    try:
        from db.supabase_client import list_themes
        from integrations.semantic_scholar import search_authors

        active_themes = list_themes(status="active", limit=5)

        for theme in active_themes:
            researchers = search_authors(theme["label"], limit=5)
            for r in researchers:
                if r.name not in seen_names:
                    profiles.append({
                        "name": r.name,
                        "signals": ["published_paper_in_theme"],
                        "theme_id": theme["id"],
                    })
                    seen_names.add(r.name)
    except Exception as exc:
        logger.warning("Failed to gather Semantic Scholar profiles: %s", exc)

    logger.info("Gathered %d tracked profiles for Founder Radar", len(profiles))
    return profiles


@app.task(name="scheduler.tasks.run_market_cartographer")
def run_market_cartographer(theme_id: str, theme_label: str) -> dict:
    """On-demand task: build a market map for a specific theme."""
    import asyncio

    from agents.market_cartographer import build_market_map

    logger.info("Celery: building market map for '%s'", theme_label)
    market_map = asyncio.run(build_market_map(theme_id, theme_label))

    return {
        "theme_id": theme_id,
        "company_count": market_map.company_count,
        "tam_estimate": market_map.tam_estimate,
        "tam_confidence": market_map.tam_confidence,
    }
