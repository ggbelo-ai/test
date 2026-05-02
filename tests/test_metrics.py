"""Tests for NAV unitization, drawdown, and XIRR."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from insider_bot import metrics
from insider_bot.metrics import CashFlow


def test_unitized_nav_no_contribution_tracks_value():
    idx = pd.date_range("2024-01-01", periods=4)
    values = pd.Series([100, 110, 121, 121], index=idx)
    contribs = [CashFlow(when=idx[0].date(), amount=-100)]
    nav = metrics.unitized_nav(values, contribs)
    assert nav.iloc[0] == 1.0
    assert nav.iloc[1] == 1.1
    assert nav.iloc[2] == 1.21


def test_unitized_nav_contribution_does_not_affect_nav():
    # Day 1: $100 → $110 (10% return). Day 2: contribute $100, value goes $210.
    # Unitized NAV should still show 10% gain at day 1 and unchanged at day 2.
    idx = pd.date_range("2024-01-01", periods=3)
    values = pd.Series([100, 110, 210], index=idx)
    contribs = [
        CashFlow(when=idx[0].date(), amount=-100),
        CashFlow(when=idx[2].date(), amount=-100),
    ]
    nav = metrics.unitized_nav(values, contribs)
    # NAV per unit on day 2 should equal day-1 NAV (no real return that day).
    assert nav.iloc[1] == 1.1
    assert nav.iloc[2] == 1.1


def test_max_drawdown_negative():
    series = pd.Series([1.0, 1.2, 0.9, 1.5])
    dd = metrics.max_drawdown(series)
    assert dd == (0.9 / 1.2) - 1.0


def test_xirr_simple_double_in_one_year():
    flows = [
        CashFlow(when=date(2024, 1, 1), amount=-100),
        CashFlow(when=date(2025, 1, 1), amount=200),
    ]
    irr = metrics.xirr(flows)
    assert irr is not None
    assert abs(irr - 1.0) < 0.01


def test_xirr_returns_none_when_no_sign_change():
    flows = [CashFlow(when=date(2024, 1, 1), amount=-100)]
    assert metrics.xirr(flows) is None
