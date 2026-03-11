"""Tests for the LangGraph-based orchestrator."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agents.orchestrator import (
    AgentState,
    FOUNDER_SIGNAL_TELEGRAM_THRESHOLD,
    THEME_NOVELTY_TELEGRAM_THRESHOLD,
    build_orchestrator_graph,
    classify_task,
    route_by_task_type,
    update_memo_founder,
    update_memo_theme,
)


class TestClassifyTask:
    def test_valid_theme_task(self):
        state: AgentState = {"task_type": "new_theme", "data": {"label": "Test"}}
        result = classify_task(state)
        assert result.get("error") is None

    def test_valid_founder_task(self):
        state: AgentState = {"task_type": "founder_alert", "data": {"name": "Jane"}}
        result = classify_task(state)
        assert result.get("error") is None

    def test_invalid_task_type(self):
        state: AgentState = {"task_type": "unknown", "data": {}}
        result = classify_task(state)
        assert result["error"] is not None
        assert "unknown" in result["error"].lower()


class TestRouteByTaskType:
    def test_routes_theme(self):
        state: AgentState = {"task_type": "new_theme", "data": {}}
        assert route_by_task_type(state) == "update_memo_theme"

    def test_routes_founder(self):
        state: AgentState = {"task_type": "founder_alert", "data": {}}
        assert route_by_task_type(state) == "update_memo_founder"

    def test_routes_error_to_end(self):
        state: AgentState = {"task_type": "new_theme", "data": {}, "error": "Something broke"}
        assert route_by_task_type(state) == "end"

    def test_routes_unknown_to_end(self):
        state: AgentState = {"task_type": "garbage", "data": {}}
        assert route_by_task_type(state) == "end"


class TestUpdateMemoTheme:
    @patch("agents.orchestrator.living_memo")
    def test_adds_new_thesis(self, mock_memo):
        mock_memo.get_thesis.return_value = None

        state: AgentState = {
            "task_type": "new_theme",
            "data": {
                "id": "test-id",
                "label": "Test Theme",
                "novelty_score": 0.85,
                "signal_maturity": "early_commercial",
            },
        }
        result = update_memo_theme(state)
        assert result["memo_updated"] is True
        mock_memo.add_thesis.assert_called_once()

    @patch("agents.orchestrator.living_memo")
    def test_updates_existing_thesis(self, mock_memo):
        mock_memo.get_thesis.return_value = {"theme_id": "test-id", "label": "Old"}

        state: AgentState = {
            "task_type": "new_theme",
            "data": {"id": "test-id", "novelty_score": 0.9, "signal_maturity": "accelerating"},
        }
        result = update_memo_theme(state)
        assert result["memo_updated"] is True
        mock_memo.update_thesis.assert_called_once()


class TestUpdateMemoFounder:
    @patch("agents.orchestrator.living_memo")
    def test_adds_founder_to_watchlist(self, mock_memo):
        state: AgentState = {
            "task_type": "founder_alert",
            "data": {
                "name": "Jane Smith",
                "signal_score": 67,
                "likely_theme_id": "theme-1",
                "recommended_action": "reach_out_now",
            },
        }
        result = update_memo_founder(state)
        assert result["memo_updated"] is True
        mock_memo.add_watch_founder.assert_called_once()


class TestGraphBuilds:
    def test_graph_compiles(self):
        graph = build_orchestrator_graph()
        compiled = graph.compile()
        assert compiled is not None

    def test_orchestrator_app_exists(self):
        from agents.orchestrator import orchestrator_app
        assert orchestrator_app is not None
