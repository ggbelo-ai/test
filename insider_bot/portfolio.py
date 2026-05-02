"""Paper portfolio: $1,000 fixed-notional entries, mark-to-market, no exits."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from . import config, db, prices
from .signals import Signal

log = logging.getLogger(__name__)


@dataclass
class Position:
    id: int
    ticker: str
    entry_date: str
    entry_price: float
    notional: float
    shares: float
    confidence: float
    insider_count: int
    purchase_value: float
    last_price: float | None
    last_marked: str | None
    rationale: str | None
    closed: bool

    @property
    def market_value(self) -> float:
        if self.last_price is None:
            return self.shares * self.entry_price
        return self.shares * self.last_price

    @property
    def pnl(self) -> float:
        return self.market_value - self.notional

    @property
    def pnl_pct(self) -> float:
        return (self.market_value / self.notional) - 1.0 if self.notional else 0.0


def has_open_position(ticker: str) -> bool:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM paper_positions WHERE ticker = ? AND closed = 0 LIMIT 1",
            (ticker,),
        ).fetchone()
    return row is not None


def open_paper_position(
    signal: Signal,
    *,
    entry_price: float,
    entry_date: date,
) -> int | None:
    """Open a new $1,000 paper trade. Returns new id, or None if a dup exists."""
    if has_open_position(signal.ticker):
        return None
    if entry_price <= 0:
        return None
    notional = config.PAPER_TRADE_NOTIONAL
    shares = notional / entry_price
    with db.connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO paper_positions (
                ticker, entry_date, entry_price, notional, shares, confidence,
                insider_count, purchase_value, last_price, last_marked, rationale
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal.ticker,
                entry_date.isoformat(),
                entry_price,
                notional,
                shares,
                signal.confidence,
                signal.cluster.distinct_insiders,
                signal.cluster.total_value,
                entry_price,
                entry_date.isoformat(),
                signal.rationale,
            ),
        )
        return cursor.lastrowid


def list_open_positions() -> list[Position]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM paper_positions WHERE closed = 0 ORDER BY entry_date DESC"
        ).fetchall()
    return [
        Position(
            id=r["id"],
            ticker=r["ticker"],
            entry_date=r["entry_date"],
            entry_price=r["entry_price"],
            notional=r["notional"],
            shares=r["shares"],
            confidence=r["confidence"],
            insider_count=r["insider_count"],
            purchase_value=r["purchase_value"],
            last_price=r["last_price"],
            last_marked=r["last_marked"],
            rationale=r["rationale"],
            closed=bool(r["closed"]),
        )
        for r in rows
    ]


def mark_to_market() -> int:
    """Update last_price for each open position from cached prices."""
    positions = list_open_positions()
    updated = 0
    for p in positions:
        latest = prices.latest_close(p.ticker)
        if not latest:
            continue
        last_date, last_price = latest
        with db.connect() as conn:
            conn.execute(
                "UPDATE paper_positions SET last_price = ?, last_marked = ? "
                "WHERE id = ?",
                (last_price, last_date, p.id),
            )
        updated += 1
    return updated


def aggregate_pnl() -> tuple[float, float, int]:
    positions = list_open_positions()
    notional = sum(p.notional for p in positions)
    market = sum(p.market_value for p in positions)
    return notional, market, len(positions)
