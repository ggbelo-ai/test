"""Twitter/X API integration — monitor bio changes, follower graphs, and engagement patterns.

Uses the Twitter API v2 free tier (limited to basic endpoints).
For higher volume, upgrade to Basic ($100/mo) or Pro tier.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

TWITTER_API_BASE = "https://api.twitter.com/2"

# Keywords that suggest a founder is in stealth mode
STEALTH_BIO_KEYWORDS = [
    "building something",
    "stealth",
    "something new",
    "working on",
    "coming soon",
    "pre-launch",
    "day 0",
    "day one",
    "ex-",
    "formerly",
    "left",
]


@dataclass
class TwitterProfile:
    """A Twitter/X user profile snapshot."""

    user_id: str
    username: str
    name: str
    bio: str
    followers_count: int
    following_count: int
    tweet_count: int
    location: str = ""
    url: str = ""
    verified: bool = False
    created_at: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class TwitterSignal:
    """A signal derived from Twitter/X activity."""

    username: str
    signal_type: str  # 'bio_change_stealth', 'follower_spike', 'engagement_shift'
    description: str
    confidence: float = 0.0
    source: str = "twitter"
    metadata: dict = field(default_factory=dict)

    @property
    def source_ref(self) -> str:
        return f"twitter:{self.username}"


def _get_headers() -> dict:
    """Return auth headers for Twitter API v2."""
    token = os.environ.get("TWITTER_BEARER_TOKEN", "")
    if not token:
        raise RuntimeError("TWITTER_BEARER_TOKEN not set")
    return {"Authorization": f"Bearer {token}"}


def fetch_user_profile(username: str) -> TwitterProfile | None:
    """Fetch a Twitter user's current profile.

    Args:
        username: Twitter handle (without @).

    Returns:
        TwitterProfile or None if not found/rate-limited.
    """
    url = f"{TWITTER_API_BASE}/users/by/username/{username}"
    params = {
        "user.fields": "description,public_metrics,location,url,verified,created_at",
    }

    try:
        resp = httpx.get(url, headers=_get_headers(), params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json().get("data", {})

        if not data:
            return None

        metrics = data.get("public_metrics", {})
        return TwitterProfile(
            user_id=data["id"],
            username=data["username"],
            name=data.get("name", ""),
            bio=data.get("description", ""),
            followers_count=metrics.get("followers_count", 0),
            following_count=metrics.get("following_count", 0),
            tweet_count=metrics.get("tweet_count", 0),
            location=data.get("location", ""),
            url=data.get("url", ""),
            verified=data.get("verified", False),
            created_at=data.get("created_at", ""),
        )
    except httpx.HTTPError as exc:
        logger.error("Twitter API failed for @%s: %s", username, exc)
        return None


def detect_stealth_bio(current_bio: str, previous_bio: str | None = None) -> TwitterSignal | None:
    """Detect if a Twitter bio suggests stealth/building mode.

    Args:
        current_bio: Current bio text.
        previous_bio: Previous bio text (for change detection). If None, only checks current.

    Returns:
        TwitterSignal if stealth pattern detected, None otherwise.
    """
    bio_lower = current_bio.lower()
    matched_keywords = [kw for kw in STEALTH_BIO_KEYWORDS if kw in bio_lower]

    if not matched_keywords:
        return None

    # Higher confidence if bio changed recently
    confidence = 0.5 + (0.1 * len(matched_keywords))
    if previous_bio and previous_bio.lower() != bio_lower:
        confidence = min(confidence + 0.2, 1.0)

    return TwitterSignal(
        username="",  # filled by caller
        signal_type="bio_change_stealth",
        description=f"Bio contains stealth indicators: {', '.join(matched_keywords)}",
        confidence=confidence,
        metadata={"matched_keywords": matched_keywords, "bio_text": current_bio},
    )


def detect_follower_spike(
    current_followers: int,
    previous_followers: int,
    threshold_pct: float = 20.0,
) -> TwitterSignal | None:
    """Detect significant follower count changes.

    Args:
        current_followers: Current follower count.
        previous_followers: Previous follower count (from last check).
        threshold_pct: Minimum percentage change to trigger signal.

    Returns:
        TwitterSignal if spike detected, None otherwise.
    """
    if previous_followers <= 0:
        return None

    change_pct = ((current_followers - previous_followers) / previous_followers) * 100

    if abs(change_pct) < threshold_pct:
        return None

    return TwitterSignal(
        username="",
        signal_type="follower_spike",
        description=f"Follower count changed {change_pct:+.1f}% ({previous_followers} → {current_followers})",
        confidence=min(abs(change_pct) / 100, 1.0),
        metadata={
            "previous_followers": previous_followers,
            "current_followers": current_followers,
            "change_pct": round(change_pct, 2),
        },
    )


def monitor_profiles(
    usernames: list[str],
    previous_snapshots: dict[str, TwitterProfile] | None = None,
) -> list[TwitterSignal]:
    """Monitor a list of Twitter profiles for founder signals.

    Args:
        usernames: List of Twitter handles to check.
        previous_snapshots: Dict of username → previous TwitterProfile for change detection.

    Returns:
        List of detected TwitterSignals.
    """
    previous = previous_snapshots or {}
    signals: list[TwitterSignal] = []

    for username in usernames:
        profile = fetch_user_profile(username)
        if not profile:
            continue

        prev = previous.get(username)

        # Check for stealth bio
        bio_signal = detect_stealth_bio(
            profile.bio,
            prev.bio if prev else None,
        )
        if bio_signal:
            bio_signal.username = username
            signals.append(bio_signal)

        # Check for follower spike
        if prev:
            follower_signal = detect_follower_spike(
                profile.followers_count,
                prev.followers_count,
            )
            if follower_signal:
                follower_signal.username = username
                signals.append(follower_signal)

    logger.info("Monitored %d Twitter profiles, found %d signals", len(usernames), len(signals))
    return signals
