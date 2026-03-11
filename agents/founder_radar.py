"""Agent 3 — Founder Radar.

Tracks high-signal founders before they announce a company — monitoring career
transitions, research outputs, and behavioural signals.

Schedule: Weekly + on-demand when a new theme is created.
Escalation: Routes to Orchestrator if signal_score > 40.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from db.supabase_client import insert_founder, link_founder_to_theme
from integrations.github import fetch_user_repos

logger = logging.getLogger(__name__)

# Signal weights for founder scoring
FOUNDER_SIGNALS = {
    "repeat_founder": 25,             # Previously exited a company
    "twitter_bio_change_to_stealth": 20,  # Changed bio to "Building something new"
    "ex_tier1_company_departure": 15,  # Left DeepMind, OpenAI, Stripe, etc.
    "published_paper_in_theme": 12,    # Academic authority in the theme
    "open_source_repo_created": 10,    # Started new technical project
    "github_contribution_spike": 8,    # Sudden activity increase on theme repos
}

# Tier-1 companies for departure detection
TIER1_COMPANIES = {
    "deepmind", "openai", "anthropic", "google brain", "meta ai", "fair",
    "stripe", "airbnb", "uber", "coinbase", "figma", "notion", "linear",
    "vercel", "datadog", "snowflake", "databricks", "scale ai",
}

SIGNAL_SCORE_THRESHOLD = 40


@dataclass
class FounderProfile:
    """A tracked founder profile with signal scoring."""

    name: str
    signal_score: int = 0
    signals_detected: list[str] = field(default_factory=list)
    twitter_handle: str | None = None
    github_username: str | None = None
    linkedin_url: str | None = None
    likely_theme_id: str | None = None
    recommended_action: str = "watch"
    draft_outreach: str = ""
    metadata: dict = field(default_factory=dict)


def score_founder(signals: list[str]) -> int:
    """Score a founder based on detected signals.

    Args:
        signals: List of signal keys from FOUNDER_SIGNALS.

    Returns:
        Total signal score.
    """
    return sum(FOUNDER_SIGNALS.get(s, 0) for s in signals)


def determine_action(signal_score: int) -> str:
    """Determine recommended action based on signal score."""
    if signal_score >= 60:
        return "reach_out_now"
    if signal_score >= SIGNAL_SCORE_THRESHOLD:
        return "reach_out_soon"
    if signal_score >= 20:
        return "watch"
    return "monitor"


def detect_github_signals(username: str) -> list[str]:
    """Detect founder signals from GitHub activity.

    Args:
        username: GitHub username to analyze.

    Returns:
        List of detected signal keys.
    """
    signals = []

    try:
        repos = fetch_user_repos(username)

        # Check for new repo creation (potential stealth project)
        recent_repos = [r for r in repos if r.get("created_at", "") >= "2025-01-01"]
        if recent_repos:
            signals.append("open_source_repo_created")

        # Check for contribution spike (many recently updated repos)
        recently_active = [r for r in repos if r.get("updated_at", "") >= "2025-01-01"]
        if len(recently_active) > 5:
            signals.append("github_contribution_spike")

    except Exception as exc:
        logger.warning("GitHub signal detection failed for %s: %s", username, exc)

    return signals


def detect_twitter_signals(twitter_handle: str) -> list[str]:
    """Detect founder signals from Twitter/X activity.

    Args:
        twitter_handle: Twitter handle (without @).

    Returns:
        List of detected signal keys.
    """
    signals = []

    try:
        from integrations.twitter import fetch_user_profile, detect_stealth_bio

        profile = fetch_user_profile(twitter_handle)
        if profile:
            stealth = detect_stealth_bio(profile.bio)
            if stealth:
                signals.append("twitter_bio_change_to_stealth")
    except Exception as exc:
        logger.warning("Twitter signal detection failed for @%s: %s", twitter_handle, exc)

    return signals


def detect_scholar_signals(author_name: str) -> list[str]:
    """Detect founder signals from Semantic Scholar.

    Args:
        author_name: Researcher name to search for.

    Returns:
        List of detected signal keys.
    """
    signals = []

    try:
        from integrations.semantic_scholar import (
            search_authors,
            get_author_papers,
            detect_publication_gap,
        )

        researchers = search_authors(author_name, limit=1)
        if researchers:
            papers = get_author_papers(researchers[0].author_id, limit=20, year_min=2023)
            if papers:
                signals.append("published_paper_in_theme")
            if detect_publication_gap(papers):
                # Publication gap suggests career transition
                signals.append("ex_tier1_company_departure")
    except Exception as exc:
        logger.warning("Semantic Scholar detection failed for %s: %s", author_name, exc)

    return signals


def generate_outreach_draft(profile: FounderProfile, theme_label: str | None = None) -> str:
    """Generate a draft outreach message using LLM.

    Falls back to a template if LLM is unavailable.
    """
    try:
        from integrations.llm import generate_founder_outreach
        return generate_founder_outreach(
            founder_name=profile.name,
            signals_detected=profile.signals_detected,
            theme_label=theme_label,
        )
    except Exception as exc:
        logger.warning("LLM outreach generation failed (%s) — using template", exc)
        signals_text = ", ".join(profile.signals_detected)
        return (
            f"Hi {profile.name.split()[0]},\n\n"
            f"I've been following your work and noticed some interesting signals "
            f"({signals_text}). Would love to chat about what you're building.\n\n"
            f"Best regards"
        )


def scan_founder(
    name: str,
    signals: list[str],
    theme_id: str | None = None,
    twitter_handle: str | None = None,
    github_username: str | None = None,
    linkedin_url: str | None = None,
) -> FounderProfile:
    """Score and process a single founder profile.

    Args:
        name: Founder's name.
        signals: Pre-detected signals.
        theme_id: Related theme UUID.
        twitter_handle: Twitter/X handle.
        github_username: GitHub username.
        linkedin_url: LinkedIn profile URL.

    Returns:
        Scored FounderProfile.
    """
    all_signals = list(signals)

    # Add platform-specific signals
    if github_username:
        all_signals.extend(detect_github_signals(github_username))
    if twitter_handle:
        all_signals.extend(detect_twitter_signals(twitter_handle))

    # Check Semantic Scholar for academic signals
    all_signals.extend(detect_scholar_signals(name))

    # Deduplicate
    all_signals = list(set(all_signals))

    signal_score = score_founder(all_signals)
    action = determine_action(signal_score)

    profile = FounderProfile(
        name=name,
        signal_score=signal_score,
        signals_detected=all_signals,
        twitter_handle=twitter_handle,
        github_username=github_username,
        linkedin_url=linkedin_url,
        likely_theme_id=theme_id,
        recommended_action=action,
    )

    if signal_score >= SIGNAL_SCORE_THRESHOLD:
        profile.draft_outreach = generate_outreach_draft(profile)

        # Persist to knowledge graph
        db_founder = insert_founder(
            name=name,
            twitter_handle=twitter_handle,
            github_username=github_username,
            linkedin_url=linkedin_url,
            signal_score=signal_score,
            signals_detected=all_signals,
        )

        if theme_id:
            link_founder_to_theme(db_founder["id"], theme_id)

        logger.info(
            "High-signal founder: %s (score=%d, action=%s)",
            name, signal_score, action,
        )

    return profile
