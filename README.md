# Tech Insider Signal Strategy

Research-only paper trading bot that monitors SEC Form 4 open-market insider
purchases across a curated universe of 50 large-cap technology companies.
Output is terminal-only.

See [`SPEC.md`](SPEC.md) for the full strategy description.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set a descriptive `User-Agent` for SEC EDGAR (required by their fair-use
policy):

```bash
export SEC_USER_AGENT="Your Name your.email@example.com"
```

## Commands

```bash
# Initialize the SQLite database
python -m insider_bot.cli init

# Refresh insider transactions, prices, signals, and paper portfolio
python -m insider_bot.cli refresh

# Print today's digest (top-3 signals + open paper portfolio)
python -m insider_bot.cli digest

# Print open paper positions
python -m insider_bot.cli status

# Run the historical backtest from 2020-01-01 to today
python -m insider_bot.cli backtest
```

All output is rendered as plain-text tables to stdout.

## Data sources

- **SEC EDGAR** (free, no key) — Form 4 filings, ticker→CIK mapping.
- **yfinance** (free, no key) — daily OHLCV.

## Disclaimer

Research and paper trading only. Not personalized financial advice.
