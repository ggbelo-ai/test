# Tech Insider Signal — Algorithm

A math-first reference for what the bot actually computes. Maps 1:1 to the
code in `insider_bot/`. For motivation, limitations, and roadmap see
[`SPEC.md`](SPEC.md).

---

## 1. Inputs and parameters

**Inputs**

- Form 4 filings from SEC EDGAR for each ticker in the universe.
- Daily OHLCV bars for each ticker and the benchmark `^GSPC` (S&P 500).

**Universe** — 50 tickers fixed in `config.UNIVERSE` (AAPL, MSFT, NVDA, …, XYZ).

**Parameters** (all from `insider_bot/config.py`)

| Constant | Value |
| --- | --- |
| `CLUSTER_WINDOW_DAYS` | 10 |
| `VOLUME_LOOKBACK_DAYS` | 20 |
| `VOLUME_ANOMALY_Z` | 1.5 |
| `CLUSTER_CAP` / `VALUE_CAP` / `VOLUME_CAP` / `RECENCY_CAP` | 35 / 25 / 20 / 20 |
| `BACKTEST_BASE_SCORE` | 20 |
| `SCORE_CEILING` | 100 |
| `BACKTEST_MIN_INSIDERS_OR_VALUE` | (2 insiders, $100,000) |
| `BACKTEST_MIN_CONFIDENCE` | 40 |
| `LIVE_LOOKBACK_DAYS` | 30 |
| `TOP_N` | 3 |
| `PAPER_TRADE_NOTIONAL` | $1,000 |
| `INITIAL_CAPITAL` | $10,000 |
| `FILING_CENSOR_TRADING_DAYS` | 1 |
| `BENCHMARK_TICKER` | `^GSPC` |

---

## 2. Eligibility filter (per Form 4 transaction)

A `nonDerivativeTransaction` is kept iff:

- `transactionCode` starts with `P` (open-market purchase).
- `shares > 0` and `price > 0`.
- `transactionDate` is parseable.
- Ticker is in `UNIVERSE` and reporting owner name is present.

Then `value = shares × price`.

---

## 3. Clustering (per ticker)

Two modes, both producing the same `Cluster` shape
`(window_start, window_end, distinct_insiders, txn_count, total_value, latest_txn_date, latest_filing_date)`:

**Live — `best_recent_cluster(txns, as_of)`**

1. Restrict to txns where `as_of − LIVE_LOOKBACK_DAYS ≤ transaction_date ≤ as_of`.
2. For each anchor txn `t_i`, build a candidate window
   `[t_i.date − (CLUSTER_WINDOW_DAYS − 1), t_i.date]`
   and collect all txns whose `transaction_date` falls inside it.
3. Pick the candidate that maximizes the lexicographic key
   `(distinct_insiders, total_value, txn_count, latest_txn_date)`.

**Historical — `historical_clusters(txns)`**

Sort txns by `transaction_date`, then walk forward emitting **non-overlapping**
clusters:

```
i ← 0
last_end ← None
while i < N:
    anchor ← txns[i]
    if last_end is not None and anchor.date ≤ last_end:
        i ← i + 1; continue
    window_start ← anchor.date
    window_end   ← anchor.date + (CLUSTER_WINDOW_DAYS − 1)
    members ← {t in txns[i:] : window_start ≤ t.date ≤ window_end}
    emit Cluster(members)
    last_end ← window_end
    advance i past window_end
```

---

## 4. Score components

Let `n = distinct_insiders`, `m = txn_count`, `V = total_value`.

| Component | Formula | Cap |
| --- | --- | --- |
| `cluster_score` | `min(35, 12·n + 3·max(0, m − n))` | 35 |
| `value_score` | `max(0, min(25, 4·log10(V)))` if `V > 0` else `0` | 25 |
| `volume_score` | `min(20, 6·max(0, z))` | 20 |
| `recency_score` *(live)* | `max(0, min(20, 20 − d/2))`, `d = as_of − latest_filing_date` (days) | 20 |
| `base_score` *(backtest)* | `20` | 20 |

**Volume z-score** (`volume_z_score` in `prices.py`):

Let `V_t` be the volume on the most recent trading day at or before `as_of`.
Let `μ`, `σ` be the sample mean and stdev (`ddof=1`) of the prior
`VOLUME_LOOKBACK_DAYS = 20` trading-day volumes (excluding `V_t`).

```
z = (V_t − μ) / σ
```

If fewer than 21 days of history exist, or `σ == 0` / `NaN`, `volume_score = 0`.
Negative `z` does not penalize.

**Composite confidence**

```
confidence_live     = min(100, cluster + value + volume + recency)
confidence_backtest = min(100, cluster + value + volume + 20)
```

---

## 5. Backtest filter

A historical cluster is accepted only if **both**:

- **Pre-score gate**: `distinct_insiders ≥ 2` **OR** `total_value ≥ $100,000`.
- **Post-score gate**: `confidence ≥ 40`.

The live model has no equivalent floor — it ranks all candidates and prints
the top 3.

---

## 6. Entry rule

**Live**

- `decision_date = as_of`.
- `entry_price = ` latest cached close for the ticker.
- Skip if a paper position is already open in that ticker (no pyramiding).
- `shares = $1,000 / entry_price`.

**Backtest**

- `decision_date = cluster.latest_filing_date`.
- `entry_date = ` the trading day at index `FILING_CENSOR_TRADING_DAYS = 1`
  (i.e. the **second** trading day) strictly after `decision_date` in the
  benchmark trading-day index.
- `entry_price = open(ticker, entry_date)`.
- `shares = $1,000 / entry_price`.
- Skip if `entry_date` does not exist or `entry_price ≤ 0`.

---

## 7. Paper portfolio bookkeeping

- Each entry is an external $1,000 contribution into the strategy.
- `mark_to_market` sets `last_price = ` latest cached close.
- `market_value = shares · last_price`.
- `pnl = market_value − notional`; `pnl_pct = pnl / notional`.
- **No exits, no stops, no rebalancing.**

---

## 8. Daily portfolio value series (backtest)

Let `T` = the benchmark's trading-day index.

Initial state at `T[0]`:

```
strategy_cash = $10,000
bench_cash    = $10,000
bench_units   = bench_cash / bench.open(T[0])     ; bench_cash ← 0
contributions = [(T[0].date(), −10,000)]
```

For each `ts` in `T`:

```
for each trade tr with entry_date == ts:
    bench_cash += 1,000
    bench_units += bench_cash / bench.open(ts)    ; bench_cash ← 0
    contributions.append((ts.date(), −1,000))
    # strategy contribution is recorded but immediately deployed: net cash 0

strategy_value(ts) = strategy_cash + Σ_{tr.entry_date ≤ ts} tr.shares · close(tr.ticker, ts)
benchmark_value(ts) = bench_cash + bench_units · bench.close(ts)
```

For ticker prices on dates without a bar, the lookup falls back to the most
recent close ≤ `ts`; if that fails, it falls back to `tr.entry_price`.

---

## 9. Unitized NAV (contribution-neutral)

Given a daily value series `V_t` and contributions `c_t` (positive amounts on
contribution dates, 0 otherwise):

```
units ← 0
for each (t, V_t) in order:
    c_t ← contribution on t (else 0)
    if units == 0:
        units ← max(V_t, c_t)
        NAV_t ← 1.0
    else:
        pre_value ← V_t − c_t
        NAV_t ← pre_value / units
        if c_t > 0 and NAV_t > 0:
            units ← units + c_t / NAV_t
emit NAV_t
```

Final series is rebased: `NAV ← NAV / NAV_first`.

Both the strategy and the cash-flow-matched benchmark are unitized using the
same contribution schedule.

---

## 10. IRR (XIRR)

Cash flows for the strategy:

- `−10,000` on `T[0].date()`.
- `−1,000` on each trade's `entry_date`.
- `+strategy_value(T[−1])` on `T[−1].date()` (terminal redemption).

Solve for `r` in:

```
Σ_i  amount_i / (1 + r)^(days_i / 365)  =  0
```

Implementation:

1. Newton's method, ≤ 100 iterations, tolerance `1e-7`, with `r` clamped
   above `−0.999`.
2. If Newton fails to converge or NPV does not change sign, fall back to
   bisection over `r ∈ [−0.99, 10]`, ≤ 200 iterations, tolerance `1e-6`.
3. Returns `None` if there is no sign change in the cash flows (no IRR exists).

The matched-benchmark IRR uses the same dates and contribution amounts but
with `+benchmark_value(T[−1])` as the terminal flow.

`IRR_alpha = IRR_strategy − IRR_benchmark`.

---

## 11. Max drawdown

```
max_drawdown(NAV) = min_t  (NAV_t / cummax(NAV)_{≤ t}  −  1)
```

Reported on the unitized strategy NAV series.

---

## 12. Top-3 daily output (live)

```
txns ← all P-coded transactions in DB with transaction_date ≥ as_of − 30 days
group by ticker
for each ticker:
    cluster ← best_recent_cluster(ticker_txns, as_of)
    if cluster is None: skip
    signal  ← score_live(cluster, as_of)
sort signals by confidence descending
print top 3
for each of the top 3:
    if no open paper position in that ticker:
        open a $1,000 paper position at the ticker's latest cached close
```

---

## Reference: where each piece lives

| Section | File · symbol |
| --- | --- |
| Eligibility filter | `insider_bot/edgar.py` · `parse_form4` |
| Live clustering | `insider_bot/signals.py` · `best_recent_cluster` |
| Historical clustering | `insider_bot/signals.py` · `historical_clusters` |
| Score components | `insider_bot/signals.py` · `_cluster_score`, `_value_score`, `_volume_score`, `_recency_score` |
| Volume z-score | `insider_bot/prices.py` · `volume_z_score` |
| Backtest filter | `insider_bot/signals.py` · `passes_backtest_filter` + `config.BACKTEST_MIN_CONFIDENCE` |
| Live entry | `insider_bot/cli.py` · `cmd_digest`; `insider_bot/portfolio.py` · `open_paper_position` |
| Backtest entry | `insider_bot/backtest.py` · `_next_trading_day_after`, `_open_price` |
| Paper bookkeeping | `insider_bot/portfolio.py` · `Position`, `mark_to_market` |
| Daily value series | `insider_bot/backtest.py` · `run_backtest` |
| Unitized NAV | `insider_bot/metrics.py` · `unitized_nav` |
| XIRR | `insider_bot/metrics.py` · `xirr` |
| Max drawdown | `insider_bot/metrics.py` · `max_drawdown` |
