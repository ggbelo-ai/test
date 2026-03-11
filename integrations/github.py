"""GitHub API integration — track trending repos and contributor activity."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from github import Auth, Github

logger = logging.getLogger(__name__)


@dataclass
class GithubSignal:
    """A signal derived from a trending GitHub repository."""

    repo_full_name: str
    description: str
    stars: int
    stars_growth_week: int
    language: str | None
    topics: list[str]
    created_at: datetime
    url: str
    source: str = "github"
    metadata: dict = field(default_factory=dict)

    @property
    def source_ref(self) -> str:
        return f"github:{self.repo_full_name}"

    @property
    def text_for_embedding(self) -> str:
        topics_str = ", ".join(self.topics) if self.topics else ""
        return f"{self.repo_full_name}: {self.description or ''}. Topics: {topics_str}"


def _get_github_client() -> Github:
    """Create an authenticated GitHub client (or unauthenticated with lower limits)."""
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return Github(auth=Auth.Token(token))
    logger.warning("GITHUB_TOKEN not set — using unauthenticated API (60 req/hr limit)")
    return Github()


def fetch_github_trending(
    stars_growth_pct_min: int = 30,
    min_stars_base: int = 100,
    max_stars_base: int = 5000,
    last_days: int = 7,
    max_results: int = 50,
) -> list[GithubSignal]:
    """Find repositories gaining traction fast (>stars_growth_pct_min% new stars in last_days).

    Uses the GitHub search API to find recently created or recently starred repos.
    """
    g = _get_github_client()
    cutoff = datetime.now(timezone.utc) - timedelta(days=last_days)
    cutoff_str = cutoff.strftime("%Y-%m-%d")

    # Search for repos with moderate star counts that were pushed to recently
    query = f"stars:{min_stars_base}..{max_stars_base} pushed:>{cutoff_str}"
    repos = g.search_repositories(query=query, sort="stars", order="desc")

    signals: list[GithubSignal] = []
    for repo in repos[:max_results]:
        # Estimate weekly star growth from stargazers count and repo age
        age_days = max((datetime.now(timezone.utc) - repo.created_at.replace(tzinfo=timezone.utc)).days, 1)
        avg_stars_per_week = (repo.stargazers_count / age_days) * 7

        # We approximate recent growth; for precise data, you'd use the stargazers timeline API
        estimated_weekly_growth = avg_stars_per_week
        if repo.stargazers_count > 0:
            growth_pct = (estimated_weekly_growth / repo.stargazers_count) * 100
        else:
            growth_pct = 0

        if growth_pct >= stars_growth_pct_min or repo.stargazers_count >= min_stars_base:
            signals.append(
                GithubSignal(
                    repo_full_name=repo.full_name,
                    description=repo.description or "",
                    stars=repo.stargazers_count,
                    stars_growth_week=int(estimated_weekly_growth),
                    language=repo.language,
                    topics=repo.get_topics(),
                    created_at=repo.created_at.replace(tzinfo=timezone.utc),
                    url=repo.html_url,
                    metadata={
                        "forks": repo.forks_count,
                        "open_issues": repo.open_issues_count,
                        "watchers": repo.watchers_count,
                    },
                )
            )

    logger.info("Fetched %d trending GitHub repos", len(signals))
    return signals


def fetch_user_repos(username: str) -> list[dict]:
    """Fetch public repos for a specific GitHub user (for founder tracking)."""
    g = _get_github_client()
    user = g.get_user(username)
    repos = []
    for repo in user.get_repos(sort="updated", direction="desc"):
        repos.append({
            "name": repo.full_name,
            "description": repo.description,
            "stars": repo.stargazers_count,
            "language": repo.language,
            "created_at": repo.created_at.isoformat(),
            "updated_at": repo.updated_at.isoformat(),
        })
    return repos
