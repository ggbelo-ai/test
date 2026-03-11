"""Tests for the Orchestrator agent."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agents.orchestrator import (
    FOUNDER_SIGNAL_TELEGRAM_THRESHOLD,
    THEME_NOVELTY_TELEGRAM_THRESHOLD,
)


class TestOrchestratorThresholds:
    def test_theme_threshold_is_stricter_than_scanner(self):
        from agents.horizon_scanner import NOVELTY_THRESHOLD
        assert THEME_NOVELTY_TELEGRAM_THRESHOLD >= NOVELTY_THRESHOLD

    def test_founder_threshold_matches_radar(self):
        from agents.founder_radar import SIGNAL_SCORE_THRESHOLD
        assert FOUNDER_SIGNAL_TELEGRAM_THRESHOLD == SIGNAL_SCORE_THRESHOLD


class TestTelegramCardFormatting:
    def test_theme_card_format(self):
        from notifications.telegram import format_theme_card

        theme = {
            "id": "test-uuid",
            "label": "Neuromorphic edge inference",
            "novelty_score": 0.84,
            "signal_maturity": "early_commercial",
            "status": "emerging",
            "signal_sources": ["arxiv:2401.xxxxx", "github:org/repo"],
        }
        text, keyboard = format_theme_card(theme)

        assert "Neuromorphic edge inference" in text
        assert "early_commercial" in text
        assert keyboard is not None

    def test_founder_card_format(self):
        from notifications.telegram import format_founder_card

        founder = {
            "id": "test-uuid",
            "name": "Jane Smith",
            "signal_score": 67,
            "signals_detected": ["repeat_founder", "twitter_bio_change_to_stealth"],
            "twitter_handle": "janesmith",
        }
        text, keyboard = format_founder_card(founder)

        assert "Jane Smith" in text
        assert "67" in text
        assert "@janesmith" in text
        assert keyboard is not None

    def test_theme_card_buttons(self):
        from notifications.telegram import format_theme_card

        theme = {"id": "abc", "label": "Test", "novelty_score": 0.9}
        _, keyboard = format_theme_card(theme)
        buttons = keyboard.inline_keyboard[0]

        assert len(buttons) == 3
        assert "Deep-dive" in buttons[0].text
        assert "Watch" in buttons[1].text
        assert "Pass" in buttons[2].text

    def test_founder_card_buttons(self):
        from notifications.telegram import format_founder_card

        founder = {"id": "abc", "name": "Test", "signal_score": 50}
        _, keyboard = format_founder_card(founder)
        buttons = keyboard.inline_keyboard[0]

        assert len(buttons) == 3
        assert "outreach" in buttons[0].text.lower()
        assert "Watch" in buttons[1].text
        assert "Pass" in buttons[2].text
