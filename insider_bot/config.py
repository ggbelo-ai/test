"""Static configuration: universe, thresholds, paths."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "insider_bot.sqlite"
CACHE_DIR = DATA_DIR / "cache"

# SEC EDGAR fair-use policy requires a descriptive User-Agent.
SEC_USER_AGENT = os.environ.get(
    "SEC_USER_AGENT",
    "insider-bot research contact@example.com",
)

# 50-name technology universe. Order is preserved from the spec.
UNIVERSE: dict[str, str] = {
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "NVDA": "NVIDIA",
    "GOOGL": "Alphabet",
    "GOOG": "Alphabet",
    "AMZN": "Amazon",
    "META": "Meta Platforms",
    "AVGO": "Broadcom",
    "TSLA": "Tesla",
    "NFLX": "Netflix",
    "ORCL": "Oracle",
    "AMD": "Advanced Micro Devices",
    "CRM": "Salesforce",
    "ADBE": "Adobe",
    "CSCO": "Cisco",
    "NOW": "ServiceNow",
    "QCOM": "Qualcomm",
    "INTU": "Intuit",
    "IBM": "IBM",
    "TXN": "Texas Instruments",
    "AMAT": "Applied Materials",
    "UBER": "Uber",
    "SHOP": "Shopify",
    "PANW": "Palo Alto Networks",
    "ANET": "Arista Networks",
    "MU": "Micron",
    "LRCX": "Lam Research",
    "ADI": "Analog Devices",
    "KLAC": "KLA",
    "SNPS": "Synopsys",
    "CDNS": "Cadence Design Systems",
    "CRWD": "CrowdStrike",
    "PLTR": "Palantir",
    "DELL": "Dell Technologies",
    "ABNB": "Airbnb",
    "ADP": "ADP",
    "APH": "Amphenol",
    "MRVL": "Marvell",
    "FTNT": "Fortinet",
    "TEAM": "Atlassian",
    "WDAY": "Workday",
    "DDOG": "Datadog",
    "NET": "Cloudflare",
    "ZS": "Zscaler",
    "SNOW": "Snowflake",
    "MDB": "MongoDB",
    "OKTA": "Okta",
    "ROKU": "Roku",
    "COIN": "Coinbase",
    "XYZ": "Block",  # formerly SQ; ticker changed in 2025
}

# Signal parameters.
CLUSTER_WINDOW_DAYS = 10
VOLUME_LOOKBACK_DAYS = 20
VOLUME_ANOMALY_Z = 1.5

# Score caps.
CLUSTER_CAP = 35
VALUE_CAP = 25
VOLUME_CAP = 20
RECENCY_CAP = 20
BACKTEST_BASE_SCORE = 20
SCORE_CEILING = 100

# Filters.
BACKTEST_MIN_INSIDERS_OR_VALUE = (2, 100_000.0)  # at least one of these
BACKTEST_MIN_CONFIDENCE = 40

# Live monitoring.
LIVE_LOOKBACK_DAYS = 30  # how far back to consider for "recent" signals
TOP_N = 3

# Paper portfolio.
PAPER_TRADE_NOTIONAL = 1_000.0
INITIAL_CAPITAL = 10_000.0

# Backtest.
BACKTEST_START = "2020-01-01"
FILING_CENSOR_TRADING_DAYS = 1
BENCHMARK_TICKER = "^GSPC"  # S&P 500


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
