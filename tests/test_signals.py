"""Unit tests for clustering and scoring (no network, no DB)."""

from __future__ import annotations

import math
from datetime import date

import pytest

from insider_bot import config, signals
from insider_bot.signals import Cluster, TxnRow


def _txn(ticker: str, owner: str, d: str, value: float = 50_000) -> TxnRow:
    transaction_date = date.fromisoformat(d)
    return TxnRow(
        ticker=ticker,
        owner_name=owner,
        transaction_date=transaction_date,
        filing_date=transaction_date,
        code="P",
        shares=value / 100,
        price=100,
        value=value,
    )


# -- historical_clusters -----------------------------------------------------

def test_historical_clusters_groups_within_10_days():
    txns = [
        _txn("AAA", "Alice", "2024-01-02"),
        _txn("AAA", "Bob",   "2024-01-05"),
        _txn("AAA", "Carol", "2024-01-09"),
    ]
    clusters = signals.historical_clusters(txns)
    assert len(clusters) == 1
    c = clusters[0]
    assert c.distinct_insiders == 3
    assert c.txn_count == 3
    assert c.total_value == 150_000


def test_historical_clusters_splits_when_outside_window():
    txns = [
        _txn("AAA", "Alice", "2024-01-02"),
        _txn("AAA", "Alice", "2024-01-05"),
        _txn("AAA", "Bob",   "2024-02-01"),  # > 10 days later
    ]
    clusters = signals.historical_clusters(txns)
    assert len(clusters) == 2


def test_historical_clusters_empty():
    assert signals.historical_clusters([]) == []


# -- best_recent_cluster -----------------------------------------------------

def test_best_recent_cluster_picks_highest_strength():
    txns = [
        _txn("AAA", "Alice", "2024-01-02", value=10_000),
        _txn("AAA", "Bob",   "2024-01-05", value=10_000),
        _txn("AAA", "Carol", "2024-01-20", value=999_999_999),  # singleton, huge value
    ]
    cluster = signals.best_recent_cluster(txns, as_of=date(2024, 1, 25))
    # 2 distinct insiders beats 1, regardless of value, by sort priority.
    assert cluster is not None
    assert cluster.distinct_insiders == 2


def test_best_recent_cluster_respects_lookback():
    txns = [_txn("AAA", "Alice", "2024-01-02")]
    cluster = signals.best_recent_cluster(
        txns, as_of=date(2024, 6, 1), lookback_days=30
    )
    assert cluster is None


# -- scoring components ------------------------------------------------------

def _cluster(insiders: int, txns: int, value: float) -> Cluster:
    return Cluster(
        ticker="AAA",
        window_start=date(2024, 1, 1),
        window_end=date(2024, 1, 1),
        distinct_insiders=insiders,
        txn_count=txns,
        total_value=value,
        latest_txn_date=date(2024, 1, 1),
        latest_filing_date=date(2024, 1, 1),
        insiders=[f"x{i}" for i in range(insiders)],
    )


def test_cluster_score_caps_at_35():
    c = _cluster(insiders=10, txns=10, value=1_000_000)
    score = signals._cluster_score(c)
    assert score == config.CLUSTER_CAP


def test_cluster_score_rewards_repeat_buys():
    c = _cluster(insiders=2, txns=5, value=1_000)
    # 2 * 12 + (5 - 2) * 3 = 33
    assert signals._cluster_score(c) == 33


def test_value_score_uses_log10():
    c = _cluster(insiders=1, txns=1, value=1_000_000)
    expected = math.log10(1_000_000) * 4  # = 24
    assert signals._value_score(c) == pytest.approx(expected)


def test_value_score_caps_at_25():
    c = _cluster(insiders=1, txns=1, value=10**100)
    assert signals._value_score(c) == config.VALUE_CAP


def test_volume_score_zero_for_negative_z():
    assert signals._volume_score(-1.0) == 0.0
    assert signals._volume_score(None) == 0.0


def test_volume_score_caps():
    assert signals._volume_score(100.0) == config.VOLUME_CAP


def test_recency_score_decays():
    c = _cluster(1, 1, 1)
    c.latest_filing_date = date(2024, 1, 1)
    same_day = signals._recency_score(c, as_of=date(2024, 1, 1))
    later = signals._recency_score(c, as_of=date(2024, 1, 11))
    assert same_day == 20
    assert later == 15  # 20 - 10/2
    far = signals._recency_score(c, as_of=date(2024, 12, 1))
    assert far == 0


# -- backtest filter ---------------------------------------------------------

def test_backtest_filter_requires_at_least_one_threshold():
    weak = _cluster(insiders=1, txns=1, value=10_000)
    strong_by_insiders = _cluster(insiders=2, txns=2, value=10_000)
    strong_by_value = _cluster(insiders=1, txns=1, value=200_000)
    assert not signals.passes_backtest_filter(weak)
    assert signals.passes_backtest_filter(strong_by_insiders)
    assert signals.passes_backtest_filter(strong_by_value)
