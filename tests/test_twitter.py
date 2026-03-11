"""Tests for the Twitter/X integration."""

from __future__ import annotations

from integrations.twitter import (
    STEALTH_BIO_KEYWORDS,
    detect_follower_spike,
    detect_stealth_bio,
)


class TestDetectStealthBio:
    def test_detects_stealth_keywords(self):
        signal = detect_stealth_bio("Building something new in AI")
        assert signal is not None
        assert signal.signal_type == "bio_change_stealth"
        assert signal.confidence > 0

    def test_no_match_for_normal_bio(self):
        signal = detect_stealth_bio("Software engineer at Google")
        assert signal is None

    def test_multiple_keywords_increase_confidence(self):
        single = detect_stealth_bio("Building something")
        multi = detect_stealth_bio("Ex-Google, building something new, coming soon")
        assert multi is not None
        assert single is not None
        assert multi.confidence > single.confidence

    def test_bio_change_increases_confidence(self):
        no_change = detect_stealth_bio("Building something", previous_bio=None)
        with_change = detect_stealth_bio(
            "Building something",
            previous_bio="ML Engineer at DeepMind"
        )
        assert no_change is not None
        assert with_change is not None
        assert with_change.confidence > no_change.confidence

    def test_case_insensitive(self):
        signal = detect_stealth_bio("BUILDING SOMETHING NEW")
        assert signal is not None


class TestDetectFollowerSpike:
    def test_detects_significant_increase(self):
        signal = detect_follower_spike(current_followers=1500, previous_followers=1000)
        assert signal is not None
        assert signal.signal_type == "follower_spike"
        assert signal.metadata["change_pct"] == 50.0

    def test_no_signal_for_small_change(self):
        signal = detect_follower_spike(current_followers=1050, previous_followers=1000)
        assert signal is None

    def test_detects_decrease(self):
        signal = detect_follower_spike(
            current_followers=700, previous_followers=1000, threshold_pct=20
        )
        assert signal is not None

    def test_zero_previous_returns_none(self):
        signal = detect_follower_spike(current_followers=100, previous_followers=0)
        assert signal is None
