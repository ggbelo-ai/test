"""Price/volume access via yfinance, with SQLite caching."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Iterable

import pandas as pd
import yfinance as yf

from . import config, db

log = logging.getLogger(__name__)


def _to_date(value) -> str:
    if isinstance(value, str):
        return value[:10]
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def download_history(ticker: str, start: str, end: str | None = None) -> pd.DataFrame:
    """Return daily OHLCV from yfinance with a tz-naive date index."""
    end = end or (date.today() + timedelta(days=1)).isoformat()
    df = yf.download(
        ticker,
        start=start,
        end=end,
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    if df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df[["open", "high", "low", "close", "volume"]]


def upsert_prices(ticker: str, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    rows = [
        (
            ticker,
            d.strftime("%Y-%m-%d"),
            float(r.open) if pd.notna(r.open) else None,
            float(r.high) if pd.notna(r.high) else None,
            float(r.low) if pd.notna(r.low) else None,
            float(r.close) if pd.notna(r.close) else None,
            float(r.volume) if pd.notna(r.volume) else None,
        )
        for d, r in df.iterrows()
    ]
    with db.connect() as conn:
        conn.executemany(
            """
            INSERT INTO prices (ticker, date, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, date) DO UPDATE SET
                open = excluded.open,
                high = excluded.high,
                low = excluded.low,
                close = excluded.close,
                volume = excluded.volume
            """,
            rows,
        )
    return len(rows)


def refresh_prices(
    tickers: Iterable[str] | None = None,
    *,
    start: str | None = None,
) -> dict[str, int]:
    """Pull recent price history for each ticker from the last cached date."""
    tickers = list(tickers) if tickers else list(config.UNIVERSE.keys())
    counts: dict[str, int] = {}
    with db.connect() as conn:
        last_dates = {
            row["ticker"]: row["max_date"]
            for row in conn.execute(
                "SELECT ticker, MAX(date) AS max_date FROM prices GROUP BY ticker"
            ).fetchall()
        }
    for t in tickers:
        ticker_start = (
            start
            or last_dates.get(t)
            or config.BACKTEST_START
        )
        # If we already have ticker_start, advance one day to avoid rerequesting.
        if ticker_start == last_dates.get(t):
            try:
                ticker_start = (
                    datetime.strptime(ticker_start, "%Y-%m-%d") + timedelta(days=1)
                ).strftime("%Y-%m-%d")
            except ValueError:
                pass
        try:
            df = download_history(t, start=ticker_start)
        except Exception as exc:
            log.warning("yfinance failed for %s: %s", t, exc)
            counts[t] = 0
            continue
        counts[t] = upsert_prices(t, df)
    return counts


def load_prices(
    ticker: str,
    *,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    where = ["ticker = ?"]
    args: list = [ticker]
    if start:
        where.append("date >= ?")
        args.append(start)
    if end:
        where.append("date <= ?")
        args.append(end)
    sql = (
        "SELECT date, open, high, low, close, volume FROM prices "
        f"WHERE {' AND '.join(where)} ORDER BY date"
    )
    with db.connect() as conn:
        rows = conn.execute(sql, args).fetchall()
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.DataFrame([dict(r) for r in rows])
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")[["open", "high", "low", "close", "volume"]]


def latest_close(ticker: str) -> tuple[str, float] | None:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT date, close FROM prices "
            "WHERE ticker = ? AND close IS NOT NULL ORDER BY date DESC LIMIT 1",
            (ticker,),
        ).fetchone()
    if not row:
        return None
    return row["date"], float(row["close"])


def volume_z_score(
    ticker: str,
    *,
    as_of: str | None = None,
    lookback: int = config.VOLUME_LOOKBACK_DAYS,
) -> tuple[float | None, float | None]:
    """Return (volume_z_score, current_volume) using a trailing 20-day baseline.

    `as_of` is inclusive. The current_volume is the volume on as_of (or the
    latest available date <= as_of). The baseline excludes that day.
    """
    df = load_prices(ticker, end=as_of)
    if df.empty or len(df) < lookback + 1:
        return None, None
    current_volume = float(df["volume"].iloc[-1])
    baseline = df["volume"].iloc[-(lookback + 1):-1]
    if baseline.std(ddof=1) == 0 or pd.isna(baseline.std(ddof=1)):
        return None, current_volume
    z = (current_volume - baseline.mean()) / baseline.std(ddof=1)
    return float(z), current_volume
