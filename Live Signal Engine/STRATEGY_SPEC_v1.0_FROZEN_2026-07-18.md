# STRONG_EARNINGS Strategy — Frozen Specification v1.0

> **STATUS UPDATE (2026-07-19) — READ BEFORE ACTING ON ANYTHING BELOW:**
> This file is preserved unedited as the permanent v1.0 record, per its
> own governance clause below. It is NOT current guidance on its own.
> See `STRATEGY_SPEC_v1.0_CURRENT_STATUS_2026-07-19.md` for the
> authoritative current position: (1) the "147 historical events" cited
> throughout this document are superseded by a 152-event canonical
> population (`FixedWindow_PerEvent_Canonical.csv`); (2) this document's
> straddle pricing model (§8, `NEAR_EARNINGS_IV_MARKUP=1.2398`) has been
> **rejected** after recalibration against real market-quoted option
> costs — the backtest's economics reverse under real pricing; (3)
> **no ticker, including MSFT, is currently cleared to trade with real
> capital under this document's rules — paper-trade only.** The signal
> (GST z-score → earnings-adjacent price move) remains validated; only
> the straddle economics documented here do not.

**Frozen:** 2026-07-18, before observing any result from the MSFT trade
planned for 2026-07-29 (or any other live/forward trade). This document
describes the strategy **exactly as currently implemented** in this
project's code, as of this date — not an aspiration, not a rounded
summary. Every value below was re-verified against the live source files
on 2026-07-18 (line references given). If the reader finds a discrepancy
between this document and the code, **the code at the time of this freeze
is the ground truth**; treat the mismatch as a documentation bug in v1.0,
not license to informally amend the rule.

**Governance — read before touching anything below:**
> Any future change to any rule in this document — the query, the
> threshold, the window, the entry/exit timing, the pricing model, the
> sizing, or the cost assumptions — produces **v1.1**, tracked as a
> **separate forward-test starting from the date of that change**. v1.1's
> results are never retroactively merged into v1.0's track record, and
> v1.0's already-recorded results (147 historical events, the MSFT
> 2026-07-29 trade, and anything else logged under v1.0) are never
> retroactively restated under v1.1's rules. This file is not edited in
> place when the strategy changes — a new `STRATEGY_SPEC_v1.1_...md` is
> created instead, and this file stays as the permanent v1.0 record.

---

## 1. Signal input — GST query and category

- **Source:** Google Trends, via `pytrends`.
- **Query term:** the bare ticker symbol string (e.g. `"MSFT"`) — no
  qualifier, no company name, no `"<TICKER> stock"` suffix.
- **Geo:** `US`
- **Property (`gprop`):** `""` — plain Web Search (not News, Images,
  YouTube, or Froogle).
- **Category (`cat`):** `0` — All categories.
- **Granularity:** weekly. Each live pull requests a `300`-day lookback
  window (`PULL_LOOKBACK_DAYS = 300`), which is long enough that Google
  Trends returns weekly-resolution points rather than daily.
- Source: `GST_Live_Signal_Engine.py`, lines 274–277.

## 2. Z-score formula and threshold

- **Window:** trailing 12 weeks (`ROLLING_WINDOW = 12`).
- **Minimum history required:** 8 weeks (`MIN_PERIODS = 8`) before a
  z-score is computed at all.
- **Formula:**
  ```
  shifted = gst.shift(1)                       # current week excluded from its own baseline
  rolling_mean = shifted.rolling(12, min_periods=8).mean()
  rolling_std  = shifted.rolling(12, min_periods=8).std()
  z = (gst - rolling_mean) / rolling_std
  ```
  The shift-by-1 is deliberate: the current week's own GST value is never
  part of the mean/std it is scored against (no look-ahead/self-inclusion).
- **Tiers** (evaluated only once `z` is defined):
  - `z < 2.0` → no signal.
  - `2.0 <= z < 5.0` → `STANDARD` tier.
  - **`z >= 5.0` → `STRONG` tier** (`STRONG_TIER_Z_THRESHOLD = 5.0`).
- Source: `GST_Live_Signal_Engine.py`, lines 279–282, 312–323;
  `GST_Build_Foundation_AllTickers.py` lines 145–154 (identical formula,
  used for the historical/backtest series).

## 3. Earnings-proximity window — the "_EARNINGS" qualifier

- **Live (forward-looking) rule, used going forward for new signals:**
  `STRONG_EARNINGS` = `STRONG` tier (z≥5) **and** the ticker's next
  upcoming earnings date is between 0 and 5 days from today, inclusive
  (`0 <= days_to_earnings <= EARNINGS_WINDOW_DAYS`, `EARNINGS_WINDOW_DAYS
  = 5`). This is a forward-only window — it never looks at earnings dates
  in the past relative to the signal week.
  Source: `GST_Live_Signal_Engine.py` line 283, 425.
- **Historical/backtest rule, used to build the 147-event validated
  population:** a **symmetric** ±5-day window around the GST spike-week
  anchor — an earnings date qualifies if it falls anywhere in
  `[anchor − 5 days, anchor + 5 days]`, not just in the forward direction.
  Source: `GST_Earnings_Clustering_Test_2021_2025_Broad50Clear.py`,
  `in_window_flag()`, lines 59–62, called with `lo_offset=-5, hi_offset=5`.
- **This asymmetry between the live rule and the historical rule is a
  real, disclosed difference, not a mistake to silently reconcile here.**
  It is inherited as-is into v1.0. If it is ever changed to match, that
  change is itself a v1.1 event.

## 4. Entry timing rule

- **Anchor:** the Sunday-starting GST spike week (the week whose GST
  value produced the qualifying z-score).
- **Entry target date:** anchor + 2 calendar days.
- **Actual entry date:** the nearest real trading day **on or before**
  that target date (`nearest_trading_day_on_or_before`).
- Source: `GST_Straddle_Simulation_2021_2025_51Ticker.py` line 59
  (`ENTRY_OFFSET_DAYS = 2`), line 168.

## 5. Exit timing rule

- **Exit target date:** anchor + 6 calendar days.
- **Actual exit date:** the nearest real trading day **on or before**
  that target date.
- **Precision note, stated explicitly because it is easy to
  mischaracterize:** this is a **fixed offset from the GST spike-week
  anchor**, not a rule keyed directly to the actual earnings-report date.
  Since a `STRONG_EARNINGS` event requires earnings within the anchor's
  ±5/0–5 day window (Section 3), the exit typically lands somewhere
  from 1 to ~6 days after the real earnings date — usually close to "the
  next trading day or two after earnings," but that is a consequence of
  the anchor-relative rule, not the rule itself. There is no logic
  anywhere in this codebase that reads "exit on the first trading day
  after the actual earnings release."
- Source: `GST_Straddle_Simulation_2021_2025_51Ticker.py` line 60
  (`EXIT_HORIZONS = {"end_of_spike_week": 6, ...}`); this document only
  freezes the `end_of_spike_week` horizon (the one reported as the
  strategy's headline win rate/median P&L throughout this project — the
  `end_of_window` (+13 day) horizon exists in the code but is not part of
  this v1.0 freeze).

## 6. Option selection rule — synthetic ATM straddle

- **This is a priced MODEL, not a real market option-chain lookup.**
  This project has never had access to historical quoted option chains
  (disclosed repeatedly in the source scripts) — there is no real strike,
  no real bid/ask, no real listed expiry anywhere in the v1.0 backtest
  numbers (147 events, win=76.2%, median=+130.0%).
- **Notional:** normalized spot = strike = **$100** (`S = K = 100`), i.e.
  an exactly-at-the-money straddle by construction, scaled so P&L is
  reported in percentage-of-premium terms.
- **Pricing model:** Black-Scholes, `d1`/`d2` closed form, risk-free rate
  `r = 0.02` (`RISK_FREE_RATE`).
- **Time-to-expiry (`T`):** `(exit_date − entry_date).days / 365`, i.e.
  the option is modeled as expiring exactly at the exit date — a
  same-day-of-exit synthetic expiry, not a real listed monthly/weekly
  contract.
- **Entry IV (v1.0 base case):** trailing realized volatility × a
  calibrated near-earnings markup.
  - Realized vol: daily-return std over the trailing 60 trading days
    ending 7 days before the anchor (`VOL_LOOKBACK_TRADING_DAYS = 60`,
    `MIN_VOL_HISTORY_DAYS = 30` minimum), annualized (`× sqrt(252)`).
  - Markup: **1.2398×** (mean of the "near earnings" bucket in
    `Earnings Clustering Test/iv_calibration_buckets.csv`, n=25,
    std=0.2646 — reused verbatim throughout this project, never
    re-derived per-run).
- **Payout at exit:** `intrinsic = |100 × (1 + realized_cum_return) − 100|`
  — i.e. the straddle payout is exactly the magnitude of the realized
  price move over the entry→exit window, with no time-value/early-exit
  nuance (the position is modeled as held to expiry, not marked-to-market
  and closed early).
- Source: `GST_Straddle_Simulation_2021_2025_51Ticker.py` lines 62, 75–86,
  117–121, 168–200.

## 7. Position sizing rule

- **Flat $10,000 per trade** (`FLAT_POSITION_SIZE = 10_000.0`), regardless
  of z-score magnitude, ticker, or any other factor.
- **Accounting device only:** a **$100,000 starting bankroll**
  (`STARTING_CAPITAL`) is used purely to compute an equity curve for
  Sharpe/drawdown reporting — this is **not** a margin or
  concurrent-capital constraint; overlapping trades are never blocked or
  reduced in size for capital reasons.
- Source: `GST_Task4_CalendarTimePortfolio.py` lines 61, 60;
  `GST_StressTest_RealCost.py` lines 100–101 (same convention reused).

## 8. Cost/execution assumptions

### 8a. v1.0 base case (the headline 147-event numbers: win=76.2%, median=+130.0%, Sharpe=2.33)

- **Entry IV markup:** 1.2398× realized vol (Section 6).
- **Cost loading:** fair Black-Scholes value × **1.05** (`COST_LOADING`)
  — a flat, one-time 5% cost applied once at entry, nothing charged on
  exit. No bid-ask spread modeled explicitly at this stage; no execution
  delay modeled at this stage.

### 8b. Combined adverse execution-assumption scenario (the stress test)

Per the earlier relabeling: this scenario is described as "simulated
profitability remains positive under the selected adverse execution
assumptions" — it is a set of modeled adverse assumptions, not a verified
real-world worst case. Three adjustments, each individually isolable in
`GST_StressTest_RealCost.py`, run at a combined "low" and "high" setting:

1. **IV crush risk adjustment:** entry IV markup swapped from the 1.2398×
   mean to **mean + 1 std ≈ 1.5045×** realized vol (empirically grounded —
   drawn from the same calibration bucket's own std, not an arbitrary
   guess — but still a modeled proxy, not observed market IV).
2. **Bid-ask spread:** **5% (low) or 8% (high)** of premium, applied on
   **both** entry (pay `(1+spread) × fair`) and exit (receive
   `(1-spread) × intrinsic`) — replacing, not stacking with, the base
   case's flat 1.05 cost loading.
3. **Execution delay:** modeled as an adverse slippage cost equal to the
   stock's realized-vol-implied expected 1-hour move
   (`hourly_std = daily_std / sqrt(6.5 trading hours)`), added in full to
   entry cost — a full 1-sigma adverse assumption, not an average case.
   Disclosed proxy: no intraday price data exists anywhere in this
   project, so this is not a measured slippage figure.
- **Combined adverse, high setting result:** win=65.3%, median=+38.1%,
  Sharpe=1.99 (full 147-event population). Still net positive, but a
  materially smaller margin than the base case.
- Source: `GST_StressTest_RealCost.py`, full file (see script header for
  the complete disclosed reasoning behind each adjustment).

## 9. Universe note (disclosed scope boundary, not a rule change)

- The **validated evidence base** (147 `STRONG_EARNINGS` events,
  Sections 6–8's numbers) comes from a **51-ticker** historical universe
  (15 original + 36 "Broad50 Clear" tickers, unambiguous-symbol-filtered).
  MSFT is one of the original 15, with 15 of its own historical
  `STRONG_EARNINGS` events already in that population.
- The **live monitoring universe** (`GST_Live_Signal_Engine.py`) covers a
  broader **425-ticker** S&P 500-derived list (unambiguous-symbol-filtered
  from 503 constituents). A live signal firing on a ticker **outside**
  the validated 51 is evaluated against v1.0's rules exactly the same way,
  but has no ticker-specific historical track record backing it the way
  MSFT does — this is a scope/evidence-strength distinction, not a rule
  difference, and does not by itself constitute v1.1.

---

*End of v1.0 freeze. Next entry in this file series, if any, is
`STRATEGY_SPEC_v1.1_...md`.*
