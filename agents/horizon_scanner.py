"""Agent 1 — Horizon Scanner.

Continuously scans for weak signals in emerging technology and market themes
before they appear in startup databases.

Schedule: Daily at 06:00 UTC via Celery.
Escalation: Routes to Orchestrator if novelty_score > 0.70.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from db.supabase_client import insert_theme, search_themes_by_embedding
from integrations.arxiv import ArxivSignal, fetch_arxiv_papers
from integrations.github import GithubSignal, fetch_github_trending
from integrations.pytrends_client import TrendsSignal, fetch_pytrends_acceleration
from integrations.uspto import PatentSignal, fetch_patent_filings

logger = logging.getLogger(__name__)

# Novelty threshold for escalation to orchestrator
NOVELTY_THRESHOLD = 0.70


@dataclass
class Theme:
    """A discovered emerging theme."""

    label: str
    description: str
    novelty_score: float
    signal_maturity: str
    signal_sources: list[str]
    embedding: list[float] | None = None
    related_existing_themes: list[str] | None = None


def classify_signal_maturity(source_mix: set[str]) -> str:
    """Classify theme maturity based on which data sources are firing.

    | Maturity Level    | Signal Mix                                              |
    |-------------------|---------------------------------------------------------|
    | pre_commercial    | arXiv only                                              |
    | early_commercial  | arXiv + GitHub                                          |
    | accelerating      | All sources firing + first companies appearing          |
    | crowded           | High company count, mainstream press coverage detected  |
    """
    has_arxiv = "arxiv" in source_mix
    has_github = "github" in source_mix
    has_patent = "uspto" in source_mix
    has_trends = "pytrends" in source_mix

    if has_arxiv and has_github and (has_patent or has_trends):
        return "accelerating"
    if has_arxiv and has_github:
        return "early_commercial"
    if has_arxiv:
        return "pre_commercial"
    # If only non-academic sources, it may already be crowded
    if has_trends and has_github:
        return "accelerating"
    return "early_commercial"


def compute_novelty_score(
    theme_embedding: list[float],
    existing_similarities: list[dict],
) -> float:
    """Compute novelty as 1 - max_similarity to existing themes.

    A score of 1.0 means completely novel; 0.0 means identical to an existing theme.
    """
    if not existing_similarities:
        return 1.0

    max_similarity = max(
        (s.get("similarity", 0) for s in existing_similarities),
        default=0,
    )
    return round(1.0 - max_similarity, 4)


def cluster_signals(embeddings: np.ndarray, min_cluster_size: int = 3) -> list[list[int]]:
    """Cluster signal embeddings using HDBSCAN.

    Args:
        embeddings: Array of shape (n_signals, embedding_dim).
        min_cluster_size: Minimum points to form a cluster.

    Returns:
        List of clusters, each a list of signal indices.
    """
    try:
        import hdbscan

        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=min_cluster_size,
            metric="euclidean",
        )
        labels = clusterer.fit_predict(embeddings)

        clusters: dict[int, list[int]] = {}
        for idx, label in enumerate(labels):
            if label == -1:
                continue  # noise
            clusters.setdefault(label, []).append(idx)

        return list(clusters.values())
    except ImportError:
        logger.warning("hdbscan not installed — falling back to no clustering")
        return [[i] for i in range(len(embeddings))]


def embed_signals(signals: list) -> np.ndarray:
    """Embed signals using a text embedding model.

    This is a placeholder — in production, call OpenAI/Anthropic embedding API.
    """
    # TODO: Replace with actual embedding API call
    # For now, return random embeddings for structural completeness
    texts = [s.text_for_embedding for s in signals]
    logger.info("Embedding %d signals (placeholder — replace with real model)", len(texts))
    return np.random.randn(len(texts), 1536).astype(np.float32)


def scan_horizon() -> list[Theme]:
    """Run the full Horizon Scanner pipeline.

    1. Fetch signals from each source (last 24 hours)
    2. Embed signals using a text embedding model
    3. Cluster with HDBSCAN to identify emerging themes
    4. Score novelty by comparing each theme against existing knowledge graph
    5. Assign signal_maturity based on source mix
    6. Return themes with novelty_score > NOVELTY_THRESHOLD

    Returns:
        List of novel Theme objects to route to the Orchestrator.
    """
    logger.info("Starting Horizon Scanner run")

    # 1. Fetch signals from all sources
    all_signals: list = []
    all_signals.extend(fetch_arxiv_papers(last_days=1))
    all_signals.extend(fetch_github_trending(stars_growth_pct_min=30))
    all_signals.extend(fetch_patent_filings(last_days=7))

    # Get active theme labels for pytrends tracking
    from db.supabase_client import list_themes
    active_themes = list_themes(status="active")
    if active_themes:
        keywords = [t["label"] for t in active_themes[:20]]
        all_signals.extend(fetch_pytrends_acceleration(keywords))

    if not all_signals:
        logger.warning("No signals fetched — aborting scan")
        return []

    logger.info("Collected %d signals across all sources", len(all_signals))

    # 2. Embed all signals
    embeddings = embed_signals(all_signals)

    # 3. Cluster into themes
    clusters = cluster_signals(embeddings)
    logger.info("Identified %d clusters from %d signals", len(clusters), len(all_signals))

    # 4-6. Score and classify each cluster as a theme
    novel_themes: list[Theme] = []

    for cluster_indices in clusters:
        cluster_signals_list = [all_signals[i] for i in cluster_indices]
        cluster_embeddings = embeddings[cluster_indices]

        # Compute centroid embedding for the theme
        centroid = cluster_embeddings.mean(axis=0).tolist()

        # Determine source mix
        source_mix = {s.source for s in cluster_signals_list}

        # Generate theme label from the first signal (placeholder — use LLM in production)
        label = cluster_signals_list[0].text_for_embedding[:100]

        # Score novelty against existing themes
        similar_themes = search_themes_by_embedding(centroid, limit=5)
        novelty = compute_novelty_score(centroid, similar_themes)

        # Classify maturity
        maturity = classify_signal_maturity(source_mix)

        theme = Theme(
            label=label,
            description=f"Theme from {len(cluster_signals_list)} signals across {', '.join(source_mix)}",
            novelty_score=novelty,
            signal_maturity=maturity,
            signal_sources=[s.source_ref for s in cluster_signals_list],
            embedding=centroid,
            related_existing_themes=[t.get("id") for t in similar_themes] if similar_themes else [],
        )

        if novelty >= NOVELTY_THRESHOLD:
            novel_themes.append(theme)

            # Persist to knowledge graph
            insert_theme(
                label=theme.label,
                novelty_score=theme.novelty_score,
                signal_maturity=theme.signal_maturity,
                signal_sources=theme.signal_sources,
                description=theme.description,
                embedding=theme.embedding,
            )

    logger.info(
        "Horizon Scanner complete: %d themes discovered, %d novel (>%.0f%%)",
        len(clusters),
        len(novel_themes),
        NOVELTY_THRESHOLD * 100,
    )

    return novel_themes
