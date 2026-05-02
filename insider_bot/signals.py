"""Cluster Form 4 purchases into 10-day windows and score them."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Iterable, Sequence

from . import config, db, prices

log = logging.getLogger(__name__)


@dataclass
class TxnRow:
    ticker: str
    owner_name: str
    transaction_date: date
    filing_date: date
    code: str
    shares: float
    price: float
    value: float


@dataclass
class Cluster:
    ticker: str
    window_start: date
    window_end: date
    distinct_insiders: int
    txn_count: int
    total_value: float
    latest_txn_date: date
    latest_filing_date: date
    insiders: list[str] = field(default_factory=list)


@dataclass
class Signal:
    ticker: str
    cluster: Cluster
    cluster_score: float
    value_score: float
    volume_score: float
    recency_score: float
    base_score: float  # 0 for live, 20 for backtest
    confidence: float
    volume_z: float | None
    rationale: str
    decision_date: date  # when the signal becomes actionable


def _parse_date(s: str) -> date:
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


def load_purchase_txns(
    *,
    tickers: Iterable[str] | None = None,
    since: str | None = None,
) -> list[TxnRow]:
    where = ["code LIKE 'P%'", "value > 0", "price > 0"]
    args: list = []
    if tickers:
        tickers = list(tickers)
        where.append(f"ticker IN ({','.join('?' * len(tickers))})")
        args.extend(tickers)
    if since:
        where.append("transaction_date >= ?")
        args.append(since)
    sql = (
        "SELECT ticker, owner_name, transaction_date, filing_date, code, "
        "shares, price, value FROM transactions "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY ticker, transaction_date"
    )
    with db.connect() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [
        TxnRow(
            ticker=r["ticker"],
            owner_name=r["owner_name"],
            transaction_date=_parse_date(r["transaction_date"]),
            filing_date=_parse_date(r["filing_date"]),
            code=r["code"],
            shares=float(r["shares"] or 0),
            price=float(r["price"] or 0),
            value=float(r["value"] or 0),
        )
        for r in rows
    ]


# -- Cluster discovery --------------------------------------------------------

def _build_cluster(ticker: str, txns: Sequence[TxnRow]) -> Cluster:
    insiders = sorted({t.owner_name for t in txns})
    return Cluster(
        ticker=ticker,
        window_start=min(t.transaction_date for t in txns),
        window_end=max(t.transaction_date for t in txns),
        distinct_insiders=len(insiders),
        txn_count=len(txns),
        total_value=sum(t.value for t in txns),
        latest_txn_date=max(t.transaction_date for t in txns),
        latest_filing_date=max(t.filing_date for t in txns),
        insiders=insiders,
    )


def best_recent_cluster(
    txns: Sequence[TxnRow],
    *,
    as_of: date,
    window_days: int = config.CLUSTER_WINDOW_DAYS,
    lookback_days: int = config.LIVE_LOOKBACK_DAYS,
) -> Cluster | None:
    """Pick the strongest cluster ending within `lookback_days` of `as_of`.

    Strength order: distinct_insiders desc, total_value desc, txn_count desc,
    latest_txn_date desc.
    """
    if not txns:
        return None
    cutoff = as_of - timedelta(days=lookback_days)
    txns = [t for t in txns if t.transaction_date >= cutoff and t.transaction_date <= as_of]
    if not txns:
        return None
    txns = sorted(txns, key=lambda t: t.transaction_date)
    candidates: list[Cluster] = []
    for i, anchor in enumerate(txns):
        window_end = anchor.transaction_date
        window_start = window_end - timedelta(days=window_days - 1)
        members = [t for t in txns if window_start <= t.transaction_date <= window_end]
        if members:
            candidates.append(_build_cluster(members[0].ticker, members))
    if not candidates:
        return None
    candidates.sort(
        key=lambda c: (
            c.distinct_insiders,
            c.total_value,
            c.txn_count,
            c.latest_txn_date.toordinal(),
        ),
        reverse=True,
    )
    return candidates[0]


def historical_clusters(
    txns: Sequence[TxnRow],
    *,
    window_days: int = config.CLUSTER_WINDOW_DAYS,
) -> list[Cluster]:
    """Walk purchases chronologically, emitting non-overlapping clusters."""
    if not txns:
        return []
    txns = sorted(txns, key=lambda t: t.transaction_date)
    out: list[Cluster] = []
    last_end: date | None = None
    i = 0
    while i < len(txns):
        anchor = txns[i]
        if last_end is not None and anchor.transaction_date <= last_end:
            i += 1
            continue
        window_start = anchor.transaction_date
        window_end = window_start + timedelta(days=window_days - 1)
        members = [t for t in txns[i:] if window_start <= t.transaction_date <= window_end]
        if not members:
            i += 1
            continue
        out.append(_build_cluster(anchor.ticker, members))
        last_end = window_end
        # Advance i past the window.
        while i < len(txns) and txns[i].transaction_date <= window_end:
            i += 1
    return out


# -- Scoring ------------------------------------------------------------------

def _cluster_score(cluster: Cluster) -> float:
    additional = max(0, cluster.txn_count - cluster.distinct_insiders)
    raw = cluster.distinct_insiders * 12 + additional * 3
    return float(min(config.CLUSTER_CAP, raw))


def _value_score(cluster: Cluster) -> float:
    if cluster.total_value <= 0:
        return 0.0
    raw = math.log10(cluster.total_value) * 4
    return float(max(0.0, min(config.VALUE_CAP, raw)))


def _volume_score(volume_z: float | None) -> float:
    if volume_z is None or volume_z <= 0:
        return 0.0
    return float(min(config.VOLUME_CAP, volume_z * 6))


def _recency_score(cluster: Cluster, as_of: date) -> float:
    days = (as_of - cluster.latest_filing_date).days
    raw = config.RECENCY_CAP - days / 2
    return float(max(0.0, min(config.RECENCY_CAP, raw)))


def _rationale(cluster: Cluster, volume_z: float | None) -> str:
    bits: list[str] = []
    bits.append(
        f"{cluster.distinct_insiders} insider"
        f"{'s' if cluster.distinct_insiders != 1 else ''} purchasing"
    )
    bits.append(
        f"{cluster.txn_count} open-market purchase"
        f"{'s' if cluster.txn_count != 1 else ''}"
    )
    bits.append(f"${cluster.total_value:,.0f} disclosed")
    if cluster.distinct_insiders >= 2:
        bits.append("cluster confirmed")
    if volume_z is not None and volume_z > config.VOLUME_ANOMALY_Z:
        bits.append(f"volume anomaly z={volume_z:.1f}")
    elif volume_z is not None:
        bits.append(f"volume z={volume_z:+.1f}")
    return "; ".join(bits)


def score_live(cluster: Cluster, *, as_of: date) -> Signal:
    z, _ = prices.volume_z_score(cluster.ticker, as_of=as_of.isoformat())
    cs = _cluster_score(cluster)
    vs = _value_score(cluster)
    vols = _volume_score(z)
    rs = _recency_score(cluster, as_of)
    confidence = float(min(config.SCORE_CEILING, cs + vs + vols + rs))
    return Signal(
        ticker=cluster.ticker,
        cluster=cluster,
        cluster_score=cs,
        value_score=vs,
        volume_score=vols,
        recency_score=rs,
        base_score=0.0,
        confidence=confidence,
        volume_z=z,
        rationale=_rationale(cluster, z),
        decision_date=as_of,
    )


def score_backtest(cluster: Cluster, *, decision_date: date) -> Signal:
    z, _ = prices.volume_z_score(cluster.ticker, as_of=decision_date.isoformat())
    cs = _cluster_score(cluster)
    vs = _value_score(cluster)
    vols = _volume_score(z)
    base = float(config.BACKTEST_BASE_SCORE)
    confidence = float(min(config.SCORE_CEILING, cs + vs + vols + base))
    return Signal(
        ticker=cluster.ticker,
        cluster=cluster,
        cluster_score=cs,
        value_score=vs,
        volume_score=vols,
        recency_score=0.0,
        base_score=base,
        confidence=confidence,
        volume_z=z,
        rationale=_rationale(cluster, z),
        decision_date=decision_date,
    )


# -- Live signal generation ---------------------------------------------------

def live_signals(*, as_of: date | None = None) -> list[Signal]:
    """Build one signal per ticker for the strongest cluster within lookback."""
    as_of = as_of or date.today()
    cutoff_str = (as_of - timedelta(days=config.LIVE_LOOKBACK_DAYS)).isoformat()
    txns = load_purchase_txns(since=cutoff_str)
    by_ticker: dict[str, list[TxnRow]] = {}
    for t in txns:
        by_ticker.setdefault(t.ticker, []).append(t)
    out: list[Signal] = []
    for ticker, ticker_txns in by_ticker.items():
        cluster = best_recent_cluster(ticker_txns, as_of=as_of)
        if cluster is None:
            continue
        out.append(score_live(cluster, as_of=as_of))
    out.sort(key=lambda s: s.confidence, reverse=True)
    return out


def passes_backtest_filter(cluster: Cluster) -> bool:
    min_insiders, min_value = config.BACKTEST_MIN_INSIDERS_OR_VALUE
    return cluster.distinct_insiders >= min_insiders or cluster.total_value >= min_value
