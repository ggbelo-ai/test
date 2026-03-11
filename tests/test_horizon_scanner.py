"""Tests for the Horizon Scanner agent."""

from __future__ import annotations

import numpy as np
import pytest

from agents.horizon_scanner import (
    NOVELTY_THRESHOLD,
    classify_signal_maturity,
    cluster_signals,
    compute_novelty_score,
)


class TestClassifySignalMaturity:
    def test_arxiv_only_is_pre_commercial(self):
        assert classify_signal_maturity({"arxiv"}) == "pre_commercial"

    def test_arxiv_github_is_early_commercial(self):
        assert classify_signal_maturity({"arxiv", "github"}) == "early_commercial"

    def test_all_sources_is_accelerating(self):
        assert classify_signal_maturity({"arxiv", "github", "uspto"}) == "accelerating"
        assert classify_signal_maturity({"arxiv", "github", "pytrends"}) == "accelerating"

    def test_github_trends_is_accelerating(self):
        assert classify_signal_maturity({"github", "pytrends"}) == "accelerating"

    def test_single_non_academic_is_early_commercial(self):
        assert classify_signal_maturity({"github"}) == "early_commercial"


class TestComputeNoveltyScore:
    def test_no_existing_themes_returns_1(self):
        score = compute_novelty_score([0.1] * 1536, [])
        assert score == 1.0

    def test_identical_theme_returns_0(self):
        similar = [{"similarity": 1.0}]
        score = compute_novelty_score([0.1] * 1536, similar)
        assert score == 0.0

    def test_partially_similar_returns_between_0_and_1(self):
        similar = [{"similarity": 0.6}, {"similarity": 0.3}]
        score = compute_novelty_score([0.1] * 1536, similar)
        assert 0 < score < 1
        assert score == pytest.approx(0.4, abs=0.01)

    def test_novelty_threshold_is_reasonable(self):
        assert 0.5 <= NOVELTY_THRESHOLD <= 0.9


class TestClusterSignals:
    def test_returns_list_of_clusters(self):
        # Create clearly separable clusters
        embeddings = np.vstack([
            np.random.randn(10, 5) + [5, 0, 0, 0, 0],
            np.random.randn(10, 5) + [0, 5, 0, 0, 0],
        ])
        clusters = cluster_signals(embeddings, min_cluster_size=3)
        assert isinstance(clusters, list)
        assert all(isinstance(c, list) for c in clusters)

    def test_empty_input(self):
        embeddings = np.array([]).reshape(0, 5)
        clusters = cluster_signals(embeddings)
        assert clusters == []
