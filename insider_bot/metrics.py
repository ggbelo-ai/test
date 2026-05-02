"""Backtest math: NAV from cash flows, IRR (XIRR), drawdown."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd


@dataclass
class CashFlow:
    when: date
    amount: float  # negative = contribution into the portfolio (outflow from investor)


def unitized_nav(
    daily_value: pd.Series,
    contributions: list[CashFlow],
) -> pd.Series:
    """Return a unitized NAV index that strips out external contributions.

    `daily_value` is the gross portfolio value on each date (cash + holdings).
    `contributions` are dated external inflows already reflected in
    `daily_value` on or after the contribution date. We compute the NAV per
    unit by issuing/redeeming units at each contribution.

    Returns a pd.Series indexed by date, normalised so the first valid date is
    1.0.
    """
    if daily_value.empty:
        return daily_value
    daily_value = daily_value.sort_index()
    contrib_by_date: dict[pd.Timestamp, float] = {}
    for cf in contributions:
        ts = pd.Timestamp(cf.when)
        # cash flow is recorded as positive contribution into the portfolio
        contrib_by_date[ts] = contrib_by_date.get(ts, 0.0) + abs(cf.amount)

    units = 0.0
    series: list[float] = []
    dates: list = []
    for ts, value in daily_value.items():
        contrib = contrib_by_date.get(ts, 0.0)
        if units == 0.0:
            if value <= 0 and contrib <= 0:
                continue
            # Bootstrap NAV at 1.0 — units equal opening value.
            units = max(value, contrib)
            nav_per_unit = 1.0
        else:
            pre_contrib_value = value - contrib
            nav_per_unit = pre_contrib_value / units
            if contrib > 0 and nav_per_unit > 0:
                units += contrib / nav_per_unit
        series.append(nav_per_unit)
        dates.append(ts)
    if not series:
        return pd.Series(dtype=float)
    out = pd.Series(series, index=pd.DatetimeIndex(dates))
    return out / out.iloc[0]


def max_drawdown(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    cummax = series.cummax()
    dd = series / cummax - 1.0
    return float(dd.min())


def xirr(cash_flows: list[CashFlow], *, guess: float = 0.1) -> float | None:
    """Money-weighted (XIRR) annual return solver via Newton's method."""
    if not cash_flows:
        return None
    flows = sorted(cash_flows, key=lambda c: c.when)
    t0 = flows[0].when
    days = np.array([(c.when - t0).days for c in flows], dtype=float)
    amounts = np.array([c.amount for c in flows], dtype=float)
    if (amounts > 0).sum() == 0 or (amounts < 0).sum() == 0:
        return None  # need at least one inflow and one outflow

    def npv(rate: float) -> float:
        return float(np.sum(amounts / (1.0 + rate) ** (days / 365.0)))

    def dnpv(rate: float) -> float:
        return float(
            np.sum(-days / 365.0 * amounts / (1.0 + rate) ** (days / 365.0 + 1.0))
        )

    rate = guess
    for _ in range(100):
        f = npv(rate)
        df = dnpv(rate)
        if df == 0:
            break
        new_rate = rate - f / df
        if not np.isfinite(new_rate):
            break
        if abs(new_rate - rate) < 1e-7:
            return float(new_rate)
        rate = new_rate
        if rate <= -0.999999:
            rate = -0.999
    # Bisection fallback.
    lo, hi = -0.99, 10.0
    f_lo, f_hi = npv(lo), npv(hi)
    if f_lo * f_hi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        f_mid = npv(mid)
        if abs(f_mid) < 1e-6:
            return float(mid)
        if f_lo * f_mid < 0:
            hi = mid
            f_hi = f_mid
        else:
            lo = mid
            f_lo = f_mid
    return float((lo + hi) / 2)
