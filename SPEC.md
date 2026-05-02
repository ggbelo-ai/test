# Tech Insider Signal Strategy

## Executive summary

The Tech Insider Signal Strategy is a systematic, research-only paper trading
model that monitors insider open-market purchases across a curated universe of
50 large and liquid technology-related public companies. The core hypothesis is
that open-market purchases by senior insiders may carry more signal than routine
compensation-related transactions because the insider is voluntarily deploying
personal capital into the issuer's equity. The strategy does not treat any
single insider purchase as sufficient evidence on its own. Instead, it
prioritizes clustered buying, larger disclosed purchase values, recency, and
unusual trading-volume context.

The strategy reads insider transaction data, filters for purchase transactions,
groups purchases into 10-day windows by issuer, scores each issuer-level
candidate, and paper-trades the highest-confidence names. Each new qualifying
signal opens a $1,000 paper trade, and the digest highlights the top three
current candidates. The current implementation is deliberately conservative in
one respect and deliberately simple in another: it only acts on disclosed
purchases, but it currently uses fixed-notional entries without an explicit exit
rule, stop-loss rule, or portfolio-level risk budget.

The model is designed as a signal laboratory rather than an autonomous trading
system. The purpose is to observe whether insider purchase clusters in the
technology universe are associated with attractive forward returns after
accounting for filing delay, price movement, volume context, and benchmark
performance. The strategy should not be treated as production capital
allocation until additional research validates signal persistence, turnover,
transaction costs, tax effects, exits, and robustness across market regimes.

## Strategy objective

The objective is to identify technology companies where disclosed insider
purchases appear unusually informative. The model seeks signals with several
reinforcing characteristics:

- Multiple insiders buying within a short window.
- A meaningful aggregate dollar value of disclosed purchases.
- A recent filing or transaction date.
- A trading-volume context that suggests market attention or abnormal activity.
- A price series that can support paper execution and backtesting without
  look-ahead bias.

The strategy intentionally focuses on purchases rather than sales. Insider
sales can occur for many non-informational reasons, including diversification,
liquidity, tax planning, or scheduled trading plans. Insider purchases are
narrower because the insider is using cash to increase exposure to the company.
That does not make purchases automatically predictive, but it makes them a
cleaner starting point for a systematic signal.

## Regulatory and data foundation

Corporate officers, directors, and beneficial owners of more than 10% of a
registered class of equity securities are required to report holdings and
transactions in company securities through Forms 3, 4, and 5
([SEC investor bulletin on Forms 3, 4, and 5](https://www.sec.gov/files/forms-3-4-5.pdf)).
In most cases, when an insider executes a reportable transaction, Form 4 must
be filed within two business days and discloses details such as transaction
amount and price per share. The strategy therefore treats Form 4 visibility as
the practical decision point rather than the trade date, because a model cannot
use a filing before it is public.

The implementation uses the SEC EDGAR public APIs directly:

- `https://www.sec.gov/files/company_tickers.json` — ticker → CIK mapping.
- `https://data.sec.gov/submissions/CIK{cik}.json` — recent filings per issuer.
- `https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/` — primary Form 4
  XML documents.

All three endpoints are free and require only a descriptive `User-Agent`
header. Price and volume data are sourced through `yfinance`, which is also
free and requires no API key.

## Tradable universe

The strategy currently monitors a fixed 50-name technology and
technology-adjacent universe. The list is intentionally broad enough to include
mega-cap platforms, semiconductors, infrastructure software, cybersecurity,
data platforms, and selected tech-enabled marketplace or financial
infrastructure names. The universe is not dynamically rebalanced and does not
currently attempt to reconstruct historical index membership.

| Ticker | Company |
| --- | --- |
| AAPL | Apple |
| MSFT | Microsoft |
| NVDA | NVIDIA |
| GOOGL | Alphabet |
| GOOG | Alphabet |
| AMZN | Amazon |
| META | Meta Platforms |
| AVGO | Broadcom |
| TSLA | Tesla |
| NFLX | Netflix |
| ORCL | Oracle |
| AMD | Advanced Micro Devices |
| CRM | Salesforce |
| ADBE | Adobe |
| CSCO | Cisco |
| NOW | ServiceNow |
| QCOM | Qualcomm |
| INTU | Intuit |
| IBM | IBM |
| TXN | Texas Instruments |
| AMAT | Applied Materials |
| UBER | Uber |
| SHOP | Shopify |
| PANW | Palo Alto Networks |
| ANET | Arista Networks |
| MU | Micron |
| LRCX | Lam Research |
| ADI | Analog Devices |
| KLAC | KLA |
| SNPS | Synopsys |
| CDNS | Cadence Design Systems |
| CRWD | CrowdStrike |
| PLTR | Palantir |
| DELL | Dell Technologies |
| ABNB | Airbnb |
| ADP | ADP |
| APH | Amphenol |
| MRVL | Marvell |
| FTNT | Fortinet |
| TEAM | Atlassian |
| WDAY | Workday |
| DDOG | Datadog |
| NET | Cloudflare |
| ZS | Zscaler |
| SNOW | Snowflake |
| MDB | MongoDB |
| OKTA | Okta |
| ROKU | Roku |
| COIN | Coinbase |
| XYZ | Block |

The universe should be viewed as a first operating set, not a final research
universe. The current list likely contains survivorship bias for historical
testing because it uses companies that are relevant today rather than companies
that would have been selected using only information available at each
historical point in time. A professional-grade future version should support
point-in-time universe construction, delisted names, corporate actions, and
historical liquidity filters.

## Signal definition

### Eligible transaction type

An eligible signal begins with an insider transaction whose transaction code
starts with `P` (open-market purchase), with positive reported value, positive
reported price, a valid ticker, and a valid reporting owner. The model excludes
transactions that do not look like open-market purchases, transactions without
usable value or price information, and transactions whose data cannot be mapped
to a monitored ticker.

The strategy currently does not incorporate sales, option exercises, gifts,
derivative conversions, or equity grants. This makes the signal narrower and
easier to interpret, but it also excludes potentially relevant behavior such as
insiders exercising and holding shares or avoiding discretionary sales.

### Grouping window

Purchases are grouped by ticker into 10-day windows. Within each issuer, the
model searches for the strongest recent purchase cluster by comparing:

- The number of distinct insiders in the window.
- The aggregate disclosed purchase value in the window.
- The number of purchase transactions in the window.
- The latest transaction and filing dates in the window.

For live signals, the model evaluates recent transaction data and selects the
strongest candidate window per issuer. For the historical backtest, it walks
through purchases chronologically and avoids repeatedly counting overlapping
10-day clusters as separate independent signals.

### Minimum signal quality

The historical backtest rejects weak events before scoring if they do not
satisfy at least one of these criteria:

- At least two distinct insiders bought within the 10-day event window.
- Aggregate purchase value was at least $100,000.

The backtest then requires a confidence score of at least 40 out of 100. Live
monitoring ranks candidate signals and highlights the top three current names,
but the backtest applies the explicit score floor to avoid filling the
historical portfolio with low-quality noise.

## Confidence scoring

The confidence score is a heuristic composite, not a trained statistical
probability. A score of 60 should not be interpreted as a 60% probability of
positive return. It is a ranking score that combines cluster intensity, dollar
value, volume context, and either recency or the historical event baseline.

### Live signal score

For live monitoring, the score is:

`confidence = min(100, cluster_score + value_score + volume_score + recency_score)`

| Component     | Formula                                              | Cap | Interpretation |
| ---           | ---                                                  | --: | --- |
| Cluster score | `distinct_insiders * 12 + additional_transactions * 3` |  35 | Rewards multiple insiders and repeated purchases. |
| Value score   | `log10(total_purchase_value) * 4`                    |  25 | Rewards larger disclosed dollar commitment with diminishing returns. |
| Volume score  | `max(0, volume_z_score) * 6`                         |  20 | Rewards unusually high recent volume only when above baseline. |
| Recency score | `20 - recency_days / 2`, floored at 0                |  20 | Rewards newer transaction windows. |

The live model uses a 20-day average volume baseline and sample standard
deviation to calculate volume z-score. Positive z-scores add to confidence,
while below-baseline volume does not penalize the score.

### Historical backtest score

For historical replay, the score is:

`confidence = min(100, cluster_score + value_score + volume_score + 20)`

The backtest uses a fixed 20-point base score instead of a live recency score
because every historical event is evaluated at its simulated decision date.

### Rationale text

Each signal produces a human-readable rationale that summarizes the main
drivers. The rationale includes:

- Number of distinct insiders.
- Number of open-market purchase transactions.
- Disclosed aggregate purchase value.
- Volume anomaly language if volume is more than 1.5 standard deviations above
  the 20-day baseline.
- Cluster flag language if at least two insiders bought.

## Volume context

Volume is not the core signal. It is a contextual overlay designed to identify
cases where insider buying coincides with unusually elevated market activity.
The model calculates:

`volume_z_score = (current_volume - trailing_20d_average) / trailing_20d_stdev`

A positive volume z-score increases confidence up to a maximum contribution of
20 points. A negative z-score is shown in the digest but does not reduce the
confidence score.

## Paper portfolio rules

The paper portfolio is intentionally simple:

- Each new top-three signal opens a new $1,000 paper trade.
- The entry price is the latest available price at the time the signal opens.
- The model does not place real brokerage orders.
- The model does not pyramid into an issuer if there is already an open paper
  position in the same ticker.
- Existing positions are marked to the latest price update available through
  the refresh process.

The paper portfolio is therefore a signal-tracking ledger rather than a fully
specified portfolio management strategy.

## Daily operating workflow

The recurring workflow is configured to run on weekdays before the U.S. market
opens. Each run:

1. Refreshes insider transactions, signal scores, volume context, and paper
   positions.
2. Ranks the latest signals by confidence.
3. Prints the top three candidates and the open paper portfolio to the
   terminal.

Email delivery has been intentionally deferred. Output is currently
terminal-only.

## Backtesting methodology

The backtest begins on 2020-01-01 and replays qualifying historical purchase
signals for the monitored universe. It uses a one-trading-day censor gap after
filing visibility before entering a simulated trade.

Each historical signal opens a fresh $1,000 trade. The backtest starts with
$10,000 of initial capital and treats every $1,000 signal trade as an external
capital contribution.

To address the cash-flow benchmarking challenge, the backtest reports two
benchmark views:

- Unitized NAV comparison: strategy and S&P 500 proxy compared as index series
  using time-weighted returns.
- Cash-flow-matched benchmark: the S&P 500 proxy receives the same $10,000
  initial capital and the same $1,000 contribution on every strategy signal
  date.

## Backtest outputs

| Metric | Purpose |
| --- | --- |
| Strategy NAV return | Contribution-neutral return of the insider signal strategy. |
| S&P 500 index return | Same-period benchmark index return. |
| Excess NAV return | Strategy NAV return minus benchmark index return. |
| Strategy value | Current simulated portfolio value including open holdings and cash. |
| Matched S&P 500 value | Value of the cash-flow-matched benchmark portfolio. |
| Net strategy P&L | Current strategy value minus all contributed capital. |
| Strategy IRR | Money-weighted annualized return based on strategy cash flows. |
| Matched S&P 500 IRR | Money-weighted annualized return using the same cash-flow dates. |
| IRR alpha | Strategy IRR minus matched benchmark IRR. |
| Total trades | Number of historical signal trades executed. |
| Profitable trades | Number and percentage of trades currently above entry. |
| Average trade return | Simple average return across historical signal trades. |
| Total trade capital | Aggregate $1,000 notional deployed. |
| Open trade value | Current gross market value of historical signal trades. |
| NAV max drawdown | Maximum drawdown of the unitized NAV curve. |

The trade blotter shows individual trade details, including ticker, company,
entry date, entry price, notional, confidence, insider count, disclosed
purchase value, current value, P&L, P&L percentage, and holding days.

## Current limitations

### Signal limitations

- Purchase intent is not observable.
- The model does not normalize purchase size by insider wealth or compensation.
- The model does not weight CEO or CFO purchases above director or 10% owner
  purchases.
- The model does not adjust for an insider's historical buying record.
- The model does not classify company news around the filing date.

### Backtest limitations

- The universe is fixed and may suffer survivorship bias.
- Delisted companies are not included.
- Transaction costs, bid-ask spreads, slippage, market impact, and taxes are
  not modeled.
- There is no exit rule.
- No sector or factor exposure caps.

### Operational limitations

- yfinance occasionally rate-limits or returns gaps for thinly traded tickers.
- SEC EDGAR requires a descriptive User-Agent and applies a soft 10 req/s
  limit; the implementation respects this.
- If SEC filing schemas change the parser may need updating.

## Recommended research roadmap

### Stage one: Make the signal more economically precise

- Purchase value as a percentage of prior holdings.
- Purchase value relative to reported annual compensation where available.
- Insider role weighting for CEO, CFO, founder, director, and 10% owner.
- Historical insider behavior by person and issuer.
- Repeated buyer detection.

### Stage two: Add exit and holding-period research

- Fixed holding periods of 30, 60, 90, 180, and 252 trading days.
- Exit after subsequent insider sales.
- Exit after earnings release.
- Exit when signal confidence decays below a threshold.
- Exit when the stock reaches a predefined excess-return target or drawdown
  limit.

### Stage three: Improve benchmark and factor attribution

- Nasdaq 100 proxy.
- Technology sector ETF proxy.
- Equal-weight tech universe benchmark.
- Size, momentum, quality, and beta attribution.

### Stage four: Add statistical validation

- Forward return buckets by confidence decile.
- Hit rate by holding period.
- T-statistics and bootstrap confidence intervals.
- Walk-forward testing and out-of-sample period separation.

## Governance and compliance posture

The strategy uses public filings and structured market data. It does not seek,
use, or infer material nonpublic information. It should remain framed as a
public-information research tool. Outputs are for research and paper trading
only.

## Bottom line

The strategy is a starting point for a systematic insider-buying research
workflow. Its strengths are a clear public-data foundation, a focused signal
definition, cluster-aware scoring, fixed-notional paper execution, and a
backtest presentation using unitized NAV and cash-flow-matched benchmarking.
Its main weaknesses are the lack of exits, survivorship bias, limited role
weighting, no transaction-cost model, and no statistical validation of the
confidence score.

This is research and analysis only, not personalized financial advice. Consult
a qualified financial advisor before making investment decisions.
