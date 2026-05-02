"""Command-line entry points: init, refresh, digest, status, backtest."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timedelta

from . import backtest as bt
from . import config, db, edgar, portfolio, prices, signals


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


# -- Pretty printers ----------------------------------------------------------

def _print_table(rows: list[list[str]], headers: list[str]) -> None:
    if not rows:
        print(f"  (no rows)")
        return
    cols = list(zip(*([headers] + rows)))
    widths = [max(len(str(c)) for c in col) for col in cols]
    fmt = "  " + "  ".join("{:<" + str(w) + "}" for w in widths)
    print(fmt.format(*headers))
    print("  " + "  ".join("-" * w for w in widths))
    for r in rows:
        print(fmt.format(*r))


def _money(x: float | None) -> str:
    if x is None:
        return "-"
    return f"${x:,.2f}"


def _pct(x: float | None) -> str:
    if x is None:
        return "-"
    return f"{x * 100:+.2f}%"


# -- Commands -----------------------------------------------------------------

def cmd_init(_args: argparse.Namespace) -> int:
    db.init_db()
    print(f"initialized database at {config.DB_PATH}")
    return 0


def cmd_refresh(args: argparse.Namespace) -> int:
    db.init_db()
    since: date | None = None
    if args.since:
        since = datetime.strptime(args.since, "%Y-%m-%d").date()
    elif args.lookback_days:
        since = date.today() - timedelta(days=args.lookback_days)

    print(
        f"refreshing insider transactions for {len(config.UNIVERSE)} tickers"
        f"{' since ' + since.isoformat() if since else ''}..."
    )
    txns = edgar.refresh_universe_transactions(since=since)
    print(f"  fetched {len(txns)} purchase transactions")
    if txns:
        rows = [
            (
                t.accession,
                t.ticker,
                t.cik,
                t.owner_cik,
                t.owner_name,
                t.owner_title,
                int(t.is_director),
                int(t.is_officer),
                int(t.is_ten_percent),
                t.transaction_date,
                t.filing_date,
                t.code,
                t.shares,
                t.price,
                t.value,
            )
            for t in txns
        ]
        with db.connect() as conn:
            conn.executemany(
                """
                INSERT OR IGNORE INTO transactions (
                    accession, ticker, cik, owner_cik, owner_name, owner_title,
                    is_director, is_officer, is_ten_percent, transaction_date,
                    filing_date, code, shares, price, value
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    print("refreshing prices for universe + benchmark...")
    counts = prices.refresh_prices(
        list(config.UNIVERSE.keys()) + [config.BENCHMARK_TICKER]
    )
    total = sum(counts.values())
    print(f"  upserted {total} price rows across {len(counts)} tickers")

    print("marking paper portfolio to market...")
    marked = portfolio.mark_to_market()
    print(f"  marked {marked} positions")
    return 0


def cmd_digest(args: argparse.Namespace) -> int:
    as_of = date.today() if not args.as_of else datetime.strptime(args.as_of, "%Y-%m-%d").date()
    sigs = signals.live_signals(as_of=as_of)
    print(f"\nTech Insider Signal — digest for {as_of.isoformat()}")
    print(f"Universe: {len(config.UNIVERSE)} tickers   Lookback: {config.LIVE_LOOKBACK_DAYS}d   "
          f"Cluster: {config.CLUSTER_WINDOW_DAYS}d\n")

    if not sigs:
        print("  no recent insider purchase signals.")
    else:
        top = sigs[: config.TOP_N]
        print(f"Top {len(top)} signals:\n")
        rows = [
            [
                s.ticker,
                config.UNIVERSE.get(s.ticker, ""),
                f"{s.confidence:5.1f}",
                str(s.cluster.distinct_insiders),
                str(s.cluster.txn_count),
                _money(s.cluster.total_value),
                s.cluster.latest_filing_date.isoformat(),
                f"{s.volume_z:+.1f}" if s.volume_z is not None else "-",
                s.rationale,
            ]
            for s in top
        ]
        _print_table(
            rows,
            ["TICKER", "COMPANY", "CONF", "INS", "TX", "VALUE",
             "LAST FILING", "VOL_Z", "RATIONALE"],
        )

        if not args.no_open:
            opened = []
            for s in top:
                latest = prices.latest_close(s.ticker)
                if not latest:
                    continue
                _, last_price = latest
                pid = portfolio.open_paper_position(
                    s, entry_price=last_price, entry_date=as_of
                )
                if pid is not None:
                    opened.append((s.ticker, last_price, pid))
            if opened:
                print(f"\nopened {len(opened)} new paper position(s):")
                for ticker, px, pid in opened:
                    print(f"  #{pid}  {ticker}  @ {_money(px)}")

    notional, market, count = portfolio.aggregate_pnl()
    pnl = market - notional
    print(
        f"\nPaper portfolio: {count} open  notional={_money(notional)}  "
        f"value={_money(market)}  P&L={_money(pnl)} "
        f"({_pct(pnl / notional if notional else 0)})"
    )
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    positions = portfolio.list_open_positions()
    print(f"\nOpen paper positions: {len(positions)}\n")
    if not positions:
        return 0
    rows = [
        [
            str(p.id),
            p.ticker,
            p.entry_date,
            f"{p.entry_price:.2f}",
            _money(p.notional),
            f"{p.confidence:.1f}",
            str(p.insider_count),
            f"{p.last_price:.2f}" if p.last_price else "-",
            _money(p.market_value),
            _money(p.pnl),
            _pct(p.pnl_pct),
        ]
        for p in positions
    ]
    _print_table(
        rows,
        ["ID", "TICKER", "ENTRY", "PX", "NOTIONAL", "CONF", "INS",
         "LAST", "VALUE", "P&L", "P&L%"],
    )
    notional, market, _ = portfolio.aggregate_pnl()
    print(
        f"\nTotals: notional={_money(notional)}  value={_money(market)}  "
        f"P&L={_money(market - notional)}"
    )
    return 0


def cmd_backtest(args: argparse.Namespace) -> int:
    result = bt.run_backtest(start=args.start, end=args.end)
    s = result.summary
    print("\n=== Tech Insider Signal — Historical Backtest ===")
    print(f"  Period:                  {s['start']} → {s['end']}")
    print(f"  Trades:                  {s['trades']}")
    print(f"  Profitable trades:       {s['profitable_trades']} "
          f"({s['win_rate'] * 100:.1f}%)")
    print(f"  Avg trade return:        {_pct(s['avg_trade_return'])}")
    print(f"  Total trade capital:     {_money(s['total_trade_capital'])}")
    print(f"  Open trade value:        {_money(s['open_trade_value'])}")
    print(f"  Strategy value:          {_money(s['strategy_value'])}")
    print(f"  Matched S&P 500 value:   {_money(s['matched_benchmark_value'])}")
    print(f"  Net strategy P&L:        {_money(s['net_strategy_pnl'])}")
    print(f"  Strategy NAV return:     {_pct(s['nav_strategy_return'])}")
    print(f"  S&P 500 NAV return:      {_pct(s['nav_benchmark_return'])}")
    print(f"  Excess NAV return:       {_pct(s['excess_nav_return'])}")
    print(f"  Strategy IRR:            {_pct(s['irr_strategy'])}")
    print(f"  Matched S&P 500 IRR:     {_pct(s['irr_benchmark'])}")
    print(f"  IRR alpha:               {_pct(s['irr_alpha'])}")
    print(f"  NAV max drawdown:        {_pct(s['nav_max_drawdown'])}")

    if args.show_trades and result.trades:
        print("\nTrade blotter:\n")
        rows = [
            [
                tr.ticker,
                tr.decision_date.isoformat(),
                tr.entry_date.isoformat(),
                f"{tr.entry_price:.2f}",
                _money(tr.notional),
                f"{tr.confidence:.1f}",
                str(tr.insider_count),
                _money(tr.purchase_value),
            ]
            for tr in result.trades
        ]
        _print_table(
            rows,
            ["TICKER", "DECISION", "ENTRY", "PX", "NOTIONAL", "CONF",
             "INS", "INS_VALUE"],
        )
    return 0


# -- Entry --------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="insider-bot")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="create the SQLite database")

    pr = sub.add_parser("refresh", help="fetch insider transactions and prices")
    pr.add_argument("--since", help="YYYY-MM-DD; default: incremental")
    pr.add_argument("--lookback-days", type=int, default=None)

    pd_ = sub.add_parser("digest", help="print top-3 signals and open new paper trades")
    pd_.add_argument("--as-of", help="YYYY-MM-DD")
    pd_.add_argument("--no-open", action="store_true",
                     help="do not open new paper positions, just print signals")

    sub.add_parser("status", help="show open paper positions")

    pb = sub.add_parser("backtest", help="run historical replay")
    pb.add_argument("--start", default=config.BACKTEST_START)
    pb.add_argument("--end", default=None)
    pb.add_argument("--show-trades", action="store_true")

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    handlers = {
        "init": cmd_init,
        "refresh": cmd_refresh,
        "digest": cmd_digest,
        "status": cmd_status,
        "backtest": cmd_backtest,
    }
    return handlers[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
