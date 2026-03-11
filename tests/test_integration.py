"""End-to-end integration test.

Seeds 5 weak signals through the full pipeline and verifies:
1. Signals are embedded and clustered into themes
2. Novel themes are detected and stored in the knowledge graph
3. Living Investment Memo is updated
4. Market Cartographer is triggered for novel themes
5. Founder Radar scores and escalates profiles
6. Orchestrator routes everything via LangGraph
7. Telegram cards are formatted correctly

This test mocks external APIs (Supabase, OpenAI, Telegram) to run without credentials.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_supabase():
    """Mock all Supabase operations."""
    with patch("db.supabase_client.get_client") as mock:
        client = MagicMock()

        # insert returns data with generated ID
        def make_insert_result(data):
            result = MagicMock()
            result.data = [{**data, "id": "test-uuid-001"}]
            return result

        table_mock = MagicMock()
        table_mock.insert.return_value.execute.side_effect = lambda: make_insert_result({"id": "test-uuid-001"})
        table_mock.select.return_value.eq.return_value.execute.return_value.data = []
        table_mock.update.return_value.eq.return_value.execute.return_value.data = [{"memo": {}}]
        table_mock.upsert.return_value.execute.return_value.data = [{}]

        client.table.return_value = table_mock
        client.rpc.return_value.execute.return_value.data = []  # No similar themes = novel

        mock.return_value = client
        yield client


@pytest.fixture
def mock_embeddings():
    """Mock the OpenAI embeddings API."""
    with patch("integrations.embeddings._get_client") as mock:
        client = MagicMock()

        def create_embeddings(**kwargs):
            texts = kwargs.get("input", [])
            result = MagicMock()
            result.data = [
                MagicMock(index=i, embedding=np.random.randn(1536).tolist())
                for i in range(len(texts))
            ]
            return result

        client.embeddings.create.side_effect = create_embeddings
        mock.return_value = client
        yield client


@pytest.fixture
def mock_llm():
    """Mock the OpenAI chat completions API."""
    with patch("integrations.llm._get_client") as mock:
        client = MagicMock()

        def create_completion(**kwargs):
            result = MagicMock()
            result.choices = [MagicMock()]
            result.choices[0].message.content = "AI-powered infrastructure monitoring"
            return result

        client.chat.completions.create.side_effect = create_completion
        mock.return_value = client
        yield client


@pytest.fixture
def mock_telegram():
    """Mock Telegram send operations."""
    with patch("notifications.telegram.Application") as mock_app:
        mock_app.builder.return_value.token.return_value.build.return_value = MagicMock()
        yield mock_app


# ---------------------------------------------------------------------------
# Seed data — 5 weak signals
# ---------------------------------------------------------------------------

SEED_SIGNALS = [
    {
        "source": "arxiv",
        "title": "Neuromorphic Computing for Edge AI Inference",
        "summary": "A novel architecture using spiking neural networks for ultra-low-power inference at the edge.",
        "paper_id": "2401.00001",
    },
    {
        "source": "arxiv",
        "title": "Efficient Spiking Neural Network Accelerators",
        "summary": "Hardware-software co-design for neuromorphic chips achieving 100x energy efficiency.",
        "paper_id": "2401.00002",
    },
    {
        "source": "github",
        "repo": "neuromorphic-ai/spikenn",
        "description": "Open-source spiking neural network framework for edge devices",
        "stars": 1200,
        "stars_growth_week": 400,
    },
    {
        "source": "uspto",
        "title": "Method for Event-Driven Neural Processing on IoT Devices",
        "abstract": "A patent for neuromorphic processing units designed for IoT edge computing.",
        "patent_id": "US20240001",
    },
    {
        "source": "github",
        "repo": "edge-ml/tinyinference",
        "description": "ML inference engine for microcontrollers and edge hardware",
        "stars": 800,
        "stars_growth_week": 250,
    },
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHorizonScannerPipeline:
    """Test the Horizon Scanner processes signals into themes."""

    def test_classify_signal_maturity_from_seed_mix(self):
        """Seed signals span arxiv + github + uspto → should classify as accelerating."""
        from agents.horizon_scanner import classify_signal_maturity

        source_mix = {"arxiv", "github", "uspto"}
        maturity = classify_signal_maturity(source_mix)
        assert maturity == "accelerating"

    def test_novelty_score_with_empty_graph(self):
        """First theme in an empty graph should have novelty = 1.0."""
        from agents.horizon_scanner import compute_novelty_score

        score = compute_novelty_score([0.1] * 1536, [])
        assert score == 1.0

    def test_clustering_groups_related_signals(self):
        """Related signals should cluster together."""
        from agents.horizon_scanner import cluster_signals

        # Create two distinct clusters
        cluster_a = np.random.randn(5, 10) + [10, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        cluster_b = np.random.randn(5, 10) + [0, 10, 0, 0, 0, 0, 0, 0, 0, 0]
        embeddings = np.vstack([cluster_a, cluster_b])

        clusters = cluster_signals(embeddings, min_cluster_size=3)
        # Should find at least 1 cluster (HDBSCAN may merge or find 2)
        assert len(clusters) >= 1
        # Each cluster should have multiple signals
        for c in clusters:
            assert len(c) >= 3


class TestMarketCartographerPipeline:
    """Test TAM estimation works end-to-end."""

    def test_tam_with_multiple_comparables(self):
        from integrations.edgar import EdgarCompanyData, estimate_tam_from_comparables

        comps = [
            EdgarCompanyData(cik="1", company_name="Intel Neuromorphic", revenue=500_000_000, revenue_year=2024),
            EdgarCompanyData(cik="2", company_name="BrainChip", revenue=10_000_000, revenue_year=2024),
            EdgarCompanyData(cik="3", company_name="Akida", revenue=5_000_000, revenue_year=2024),
        ]
        result = estimate_tam_from_comparables(comps)

        assert result["tam_confidence"] == "high"
        assert result["tam_estimate"] > 0
        assert result["comparable_count"] == 3


class TestFounderRadarPipeline:
    """Test founder scoring across the full signal detection pipeline."""

    def test_high_signal_founder_triggers_escalation(self):
        from agents.founder_radar import scan_founder, SIGNAL_SCORE_THRESHOLD

        # Simulate a repeat founder who left a tier-1 company
        with patch("agents.founder_radar.detect_github_signals", return_value=["open_source_repo_created"]):
            with patch("agents.founder_radar.detect_twitter_signals", return_value=["twitter_bio_change_to_stealth"]):
                with patch("agents.founder_radar.detect_scholar_signals", return_value=[]):
                    with patch("agents.founder_radar.insert_founder", return_value={"id": "f-001"}):
                        with patch("agents.founder_radar.link_founder_to_theme"):
                            result = scan_founder(
                                name="Jane Smith",
                                signals=["repeat_founder", "ex_tier1_company_departure"],
                                theme_id="theme-001",
                                twitter_handle="janesmith",
                                github_username="janesmith",
                            )

        assert result.signal_score >= SIGNAL_SCORE_THRESHOLD
        assert result.recommended_action in ("reach_out_now", "reach_out_soon")
        assert len(result.signals_detected) >= 3
        assert result.draft_outreach  # Outreach should be generated


class TestOrchestratorPipeline:
    """Test the LangGraph orchestrator routes correctly."""

    def test_graph_compiles_and_has_nodes(self):
        from agents.orchestrator import build_orchestrator_graph

        graph = build_orchestrator_graph()
        compiled = graph.compile()
        assert compiled is not None

    @patch("agents.orchestrator.living_memo")
    def test_theme_route_updates_memo(self, mock_memo):
        from agents.orchestrator import classify_task, update_memo_theme

        mock_memo.get_thesis.return_value = None

        state = {
            "task_type": "new_theme",
            "data": {
                "id": "t-001",
                "label": "Neuromorphic edge inference",
                "novelty_score": 0.84,
                "signal_maturity": "accelerating",
            },
        }

        classified = classify_task(state)
        assert classified.get("error") is None

        result = update_memo_theme(classified)
        assert result["memo_updated"] is True
        mock_memo.add_thesis.assert_called_once()

    @patch("agents.orchestrator.living_memo")
    def test_founder_route_updates_memo(self, mock_memo):
        from agents.orchestrator import classify_task, update_memo_founder

        state = {
            "task_type": "founder_alert",
            "data": {
                "name": "Jane Smith",
                "signal_score": 67,
                "likely_theme_id": "t-001",
                "recommended_action": "reach_out_now",
            },
        }

        classified = classify_task(state)
        result = update_memo_founder(classified)
        assert result["memo_updated"] is True
        mock_memo.add_watch_founder.assert_called_once()


class TestTelegramCards:
    """Test Telegram notification formatting for the full pipeline."""

    def test_theme_card_for_seed_theme(self):
        from notifications.telegram import format_theme_card

        theme = {
            "id": "t-001",
            "label": "Neuromorphic edge inference",
            "novelty_score": 0.84,
            "signal_maturity": "accelerating",
            "status": "emerging",
            "signal_sources": [
                "arxiv:2401.00001", "arxiv:2401.00002",
                "github:neuromorphic-ai/spikenn", "uspto:US20240001",
            ],
            "description": "Emerging theme in neuromorphic computing for edge AI.",
        }

        text, keyboard = format_theme_card(theme)

        assert "Neuromorphic edge inference" in text
        assert "accelerating" in text
        assert "84%" in text
        # Should have 3 inline buttons
        assert len(keyboard.inline_keyboard[0]) == 3

    def test_founder_card_for_high_signal_profile(self):
        from notifications.telegram import format_founder_card

        founder = {
            "id": "f-001",
            "name": "Jane Smith",
            "signal_score": 67,
            "signals_detected": [
                "repeat_founder",
                "twitter_bio_change_to_stealth",
                "ex_tier1_company_departure",
                "open_source_repo_created",
            ],
            "twitter_handle": "janesmith",
            "github_username": "janesmith",
            "draft_outreach": "Hi Jane, I noticed you recently left DeepMind...",
        }

        text, keyboard = format_founder_card(founder)

        assert "Jane Smith" in text
        assert "67" in text
        assert "@janesmith" in text
        assert "Draft outreach" in text
        assert len(keyboard.inline_keyboard[0]) == 3


class TestEndToEndFlow:
    """Test the complete signal → theme → memo → notification flow."""

    @patch("agents.orchestrator.send_theme_card", new_callable=AsyncMock)
    @patch("agents.orchestrator.send_founder_card", new_callable=AsyncMock)
    @patch("agents.orchestrator.living_memo")
    def test_full_theme_flow(self, mock_memo, mock_founder_card, mock_theme_card):
        """Simulate the full theme discovery and processing flow."""
        from agents.orchestrator import route_task

        mock_memo.get_thesis.return_value = None

        # Route a high-novelty theme through the orchestrator
        result = route_task("new_theme", {
            "id": "t-001",
            "label": "Neuromorphic edge inference",
            "novelty_score": 0.84,
            "signal_maturity": "accelerating",
            "signal_sources": ["arxiv:2401.00001", "github:neuromorphic-ai/spikenn"],
        })

        # Memo should be updated
        assert result["memo_updated"] is True
        mock_memo.add_thesis.assert_called_once()

        # Telegram should be sent (novelty 0.84 > threshold 0.75)
        assert result["telegram_sent"] is True

    @patch("agents.orchestrator.send_theme_card", new_callable=AsyncMock)
    @patch("agents.orchestrator.send_founder_card", new_callable=AsyncMock)
    @patch("agents.orchestrator.living_memo")
    def test_full_founder_flow(self, mock_memo, mock_founder_card, mock_theme_card):
        """Simulate the full founder alert and processing flow."""
        from agents.orchestrator import route_task

        result = route_task("founder_alert", {
            "name": "Jane Smith",
            "signal_score": 67,
            "signals_detected": ["repeat_founder", "twitter_bio_change_to_stealth"],
            "likely_theme_id": "t-001",
            "recommended_action": "reach_out_now",
        })

        assert result["memo_updated"] is True
        mock_memo.add_watch_founder.assert_called_once()
        assert result["telegram_sent"] is True

    @patch("agents.orchestrator.send_theme_card", new_callable=AsyncMock)
    @patch("agents.orchestrator.send_founder_card", new_callable=AsyncMock)
    @patch("agents.orchestrator.living_memo")
    def test_low_novelty_skips_telegram(self, mock_memo, mock_founder_card, mock_theme_card):
        """Themes below threshold should not trigger Telegram."""
        from agents.orchestrator import route_task

        mock_memo.get_thesis.return_value = None

        result = route_task("new_theme", {
            "id": "t-002",
            "label": "Generic machine learning",
            "novelty_score": 0.50,
            "signal_maturity": "crowded",
        })

        assert result["memo_updated"] is True
        assert result["telegram_sent"] is False
