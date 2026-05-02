"""Historical replay: walks Form 4 purchase clusters chronologically and
simulates $1,000 paper trades with a 1-trading-day filing-visibility censor.

Outputs unitized NAV vs S&P 500 plus a cash-flow-matched benchmark.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable

import pandas as pd

from . import config, metrics, prices, signals
from .metrics import CashFlow

log = logging.getLogger(__name__)


@dataclass
class Trade:
    ticker: str
    decision_date: date
    entry_date: date
    entry_price: float
    notional: float
    shares: float
    confidence: float
    insider_count: int
    purchase_value: float
    rationale: str
    exit_price: float | None = None
    exit_date: date | None = None

    def value_on(self, dt: date, price_lookup) -> float:
        if dt < self.entry_date:
            return 0.0
        if self.exit_date and dt >= self.exit_date and self.exit_price is not None:
            return self.shares * self.exit_price
        px = price_lookup(self.ticker, dt)
        if px is None:
            px = self.entry_price
        return self.shares * px


@dataclass
class BacktestResult:
    trades: list[Trade]
    daily_strategy_value: pd.Series
    daily_benchmark_value: pd.Series
    nav_strategy: pd.Series
    nav_benchmark: pd.Series
    contributions: list[CashFlow]
    summary: dict = field(default_factory=dict)


def _trading_days_index(start: str, end: str) -> pd.DatetimeIndex:
    bench = prices.load_prices(config.BENCHMARK_TICKER, start=start, end=end)
    return bench.index


def _next_trading_day_after(filing_date: date, trading_index: pd.DatetimeIndex) -> date | None:
    """Return the entry date = first trading day strictly after filing_date + censor gap."""
    target = pd.Timestamp(filing_date)
    available = trading_index[trading_index > target]
    if len(available) <= config.FILING_CENSOR_TRADING_DAYS:
        return None
    return available[config.FILING_CENSOR_TRADING_DAYS].date()


def _price_lookup_factory(price_cache: dict[str, pd.DataFrame]):
    def lookup(ticker: str, when: date) -> float | None:
        df = price_cache.get(ticker)
        if df is None or df.empty:
            return None
        ts = pd.Timestamp(when)
        if ts in df.index:
            return float(df.at[ts, "close"])
        # forward-fill: use last available close on or before the target.
        prior = df.index[df.index <= ts]
        if len(prior) == 0:
            return None
        return float(df.at[prior[-1], "close"])
    return lookup


def _open_price(ticker: str, when: date, df: pd.DataFrame) -> float | None:
    if df.empty:
        return None
    ts = pd.Timestamp(when)
    if ts in df.index:
        return float(df.at[ts, "open"])
    upcoming = df.index[df.index >= ts]
    if len(upcoming) == 0:
        return None
    return float(df.at[upcoming[0], "open"])


def run_backtest(
    *,
    start: str = config.BACKTEST_START,
    end: str | None = None,
) -> BacktestResult:
    end = end or date.today().isoformat()
    log.info("backtest %s → %s", start, end)

    # 1. Load all purchase txns for the universe since `start`.
    txns = signals.load_purchase_txns(
        tickers=list(config.UNIVERSE.keys()),
        since=start,
    )
    log.info("loaded %d purchase txns", len(txns))

    # 2. Build chronologically-non-overlapping clusters per ticker.
    by_ticker: dict[str, list[signals.TxnRow]] = {}
    for t in txns:
        by_ticker.setdefault(t.ticker, []).append(t)
    all_clusters: list[signals.Cluster] = []
    for ticker, ticker_txns in by_ticker.items():
        all_clusters.extend(signals.historical_clusters(ticker_txns))
    log.info("built %d clusters", len(all_clusters))

    # 3. Cache prices for tickers + benchmark.
    needed = sorted({c.ticker for c in all_clusters} | {config.BENCHMARK_TICKER})
    price_cache: dict[str, pd.DataFrame] = {
        t: prices.load_prices(t, start=start, end=end) for t in needed
    }

    bench_df = price_cache[config.BENCHMARK_TICKER]
    if bench_df.empty:
        raise RuntimeError(
            f"No price history for benchmark {config.BENCHMARK_TICKER}; "
            "run `refresh` first."
        )
    trading_index = bench_df.index

    # 4. Score and filter clusters; convert qualifying ones to trades.
    trades: list[Trade] = []
    for cluster in sorted(all_clusters, key=lambda c: c.latest_filing_date):
        if not signals.passes_backtest_filter(cluster):
            continue
        signal = signals.score_backtest(cluster, decision_date=cluster.latest_filing_date)
        if signal.confidence < config.BACKTEST_MIN_CONFIDENCE:
            continue
        entry_date = _next_trading_day_after(cluster.latest_filing_date, trading_index)
        if not entry_date:
            continue
        entry_open = _open_price(cluster.ticker, entry_date, price_cache[cluster.ticker])
        if entry_open is None or entry_open <= 0:
            continue
        notional = config.PAPER_TRADE_NOTIONAL
        shares = notional / entry_open
        trades.append(
            Trade(
                ticker=cluster.ticker,
                decision_date=cluster.latest_filing_date,
                entry_date=entry_date,
                entry_price=entry_open,
                notional=notional,
                shares=shares,
                confidence=signal.confidence,
                insider_count=cluster.distinct_insiders,
                purchase_value=cluster.total_value,
                rationale=signal.rationale,
            )
        )
    log.info("generated %d trades", len(trades))

    # 5. Build daily portfolio value series.
    lookup = _price_lookup_factory(price_cache)
    daily_strategy: dict[pd.Timestamp, float] = {}
    daily_bench_matched: dict[pd.Timestamp, float] = {}
    contributions: list[CashFlow] = []

    initial = config.INITIAL_CAPITAL
    cash_strategy = initial
    cash_bench = initial
    bench_units = 0.0  # number of S&P 500 "units" held by matched benchmark

    contributions.append(CashFlow(when=trading_index[0].date(), amount=-initial))

    # First-day boostrap: matched-benchmark buys at first trading day's open.
    first_bench_open = bench_df["open"].iloc[0]
    if first_bench_open > 0:
        bench_units = cash_bench / first_bench_open
        cash_bench = 0.0

    trades_by_date: dict[pd.Timestamp, list[Trade]] = {}
    for tr in trades:
        trades_by_date.setdefault(pd.Timestamp(tr.entry_date), []).append(tr)

    for ts in trading_index:
        # Apply contributions on this day.
        new_trades = trades_by_date.get(ts, [])
        for tr in new_trades:
            # Each trade is a fresh $1k contribution immediately deployed into
            # shares — net effect on strategy cash is zero, but we still record
            # the contribution for NAV and IRR.
            cash_bench += config.PAPER_TRADE_NOTIONAL
            bench_open = bench_df.at[ts, "open"] if ts in bench_df.index else None
            if bench_open and bench_open > 0:
                bench_units += cash_bench / bench_open
                cash_bench = 0.0
            contributions.append(
                CashFlow(when=ts.date(), amount=-config.PAPER_TRADE_NOTIONAL)
            )

        strat_holdings = sum(
            tr.value_on(ts.date(), lookup) for tr in trades if tr.entry_date <= ts.date()
        )
        daily_strategy[ts] = cash_strategy + strat_holdings
        bench_close = bench_df.at[ts, "close"] if ts in bench_df.index else None
        if bench_close is not None:
            daily_bench_matched[ts] = cash_bench + bench_units * bench_close

    strat_series = pd.Series(daily_strategy).sort_index()
    bench_series = pd.Series(daily_bench_matched).sort_index()

    # 6. NAV (unitized) for each.
    nav_strategy = metrics.unitized_nav(strat_series, contributions)
    nav_benchmark = metrics.unitized_nav(bench_series, contributions)

    # 7. Final cash flow: terminal value redemption (positive = inflow back).
    if not strat_series.empty:
        terminal_strategy = float(strat_series.iloc[-1])
        terminal_bench = float(bench_series.iloc[-1])
    else:
        terminal_strategy = 0.0
        terminal_bench = 0.0

    end_date = trading_index[-1].date()
    cf_strategy = list(contributions) + [CashFlow(when=end_date, amount=terminal_strategy)]
    cf_bench = list(contributions) + [CashFlow(when=end_date, amount=terminal_bench)]
    irr_strategy = metrics.xirr(cf_strategy)
    irr_bench = metrics.xirr(cf_bench)

    # 8. Assemble per-trade summary.
    today = trading_index[-1].date()
    profitable = 0
    trade_returns: list[float] = []
    open_value = 0.0
    for tr in trades:
        cv = tr.value_on(today, lookup)
        open_value += cv
        ret = (cv / tr.notional) - 1.0
        trade_returns.append(ret)
        if cv > tr.notional:
            profitable += 1
    total_capital = sum(tr.notional for tr in trades)
    nav_strat_return = (
        float(nav_strategy.iloc[-1] / nav_strategy.iloc[0] - 1.0) if not nav_strategy.empty else 0.0
    )
    nav_bench_return = (
        float(nav_benchmark.iloc[-1] / nav_benchmark.iloc[0] - 1.0) if not nav_benchmark.empty else 0.0
    )

    summary = {
        "start": trading_index[0].date().isoformat(),
        "end": end_date.isoformat(),
        "trades": len(trades),
        "profitable_trades": profitable,
        "win_rate": profitable / len(trades) if trades else 0.0,
        "avg_trade_return": sum(trade_returns) / len(trade_returns) if trade_returns else 0.0,
        "total_trade_capital": total_capital,
        "open_trade_value": open_value,
        "strategy_value": terminal_strategy,
        "matched_benchmark_value": terminal_bench,
        "net_strategy_pnl": terminal_strategy - (initial + total_capital),
        "nav_strategy_return": nav_strat_return,
        "nav_benchmark_return": nav_bench_return,
        "excess_nav_return": nav_strat_return - nav_bench_return,
        "irr_strategy": irr_strategy,
        "irr_benchmark": irr_bench,
        "irr_alpha": (
            irr_strategy - irr_bench
            if irr_strategy is not None and irr_bench is not None
            else None
        ),
        "nav_max_drawdown": metrics.max_drawdown(nav_strategy),
    }

    return BacktestResult(
        trades=trades,
        daily_strategy_value=strat_series,
        daily_benchmark_value=bench_series,
        nav_strategy=nav_strategy,
        nav_benchmark=nav_benchmark,
        contributions=contributions,
        summary=summary,
    )
