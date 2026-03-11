"""Tests for the Founder Radar agent."""

from __future__ import annotations

from agents.founder_radar import (
    FOUNDER_SIGNALS,
    SIGNAL_SCORE_THRESHOLD,
    determine_action,
    score_founder,
)


class TestScoreFounder:
    def test_empty_signals(self):
        assert score_founder([]) == 0

    def test_single_signal(self):
        assert score_founder(["repeat_founder"]) == 25

    def test_multiple_signals(self):
        signals = ["repeat_founder", "twitter_bio_change_to_stealth"]
        assert score_founder(signals) == 45

    def test_unknown_signal_ignored(self):
        assert score_founder(["unknown_signal"]) == 0

    def test_all_signals_sum(self):
        all_signals = list(FOUNDER_SIGNALS.keys())
        expected = sum(FOUNDER_SIGNALS.values())
        assert score_founder(all_signals) == expected

    def test_above_threshold(self):
        signals = ["repeat_founder", "ex_tier1_company_departure", "open_source_repo_created"]
        score = score_founder(signals)
        assert score == 50
        assert score >= SIGNAL_SCORE_THRESHOLD


class TestDetermineAction:
    def test_high_score_reach_out_now(self):
        assert determine_action(60) == "reach_out_now"
        assert determine_action(90) == "reach_out_now"

    def test_medium_score_reach_out_soon(self):
        assert determine_action(40) == "reach_out_soon"
        assert determine_action(59) == "reach_out_soon"

    def test_low_score_watch(self):
        assert determine_action(20) == "watch"
        assert determine_action(39) == "watch"

    def test_very_low_score_monitor(self):
        assert determine_action(0) == "monitor"
        assert determine_action(19) == "monitor"
