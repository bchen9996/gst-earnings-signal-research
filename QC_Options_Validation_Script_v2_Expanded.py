# ============================================================================
# QuantConnect Research validation, EXPANDED SAMPLE (v2): real historical
# option quotes vs. this project's Black-Scholes-modeled entry/exit prices,
# for an 80-100 event PROPER STRATIFIED RANDOM sample of the 152-event
# FixedWindow_PerEvent_Canonical.csv population.
#
# WHAT CHANGED FROM THE FIRST VALIDATION SCRIPT (n=42, top-winner/loser
# biased):
#   1. SAMPLING: this sample (n=90) is NOT biased toward top winners/losers
#      -- it's a ticker-proportional stratified random sample (each of the
#      27 tickers with >=1 qualifying canonical event gets a share of the
#      sample proportional to its share of the 152-event population,
#      floored at 1 per ticker, largest-remainder rounding to hit the
#      n=90 target, random draw within each ticker via a fixed seed=7,
#      distinct from the prior sample's seed=42 to avoid any overlap bias).
#      All 27 tickers with qualifying events are represented. Year spread
#      (2021: 12, 2022: 16, 2023: 22, 2024: 22, 2025: 18) tracks the
#      population's own year distribution (21/25/38/36/32) proportionally
#      -- not deliberately re-balanced across years, since proportional
#      representation of the true population is the actual goal here, not
#      an artificially even year split.
#   2. AUTOMATED CORRUPTION DETECTION: the first validation run found ONE
#      corrupted event (NFLX 2025-01-19, real_cost_pct_of_spot=719%, a
#      broken strike/expiry match) only because a human spotted an
#      obviously-wrong number after the fact. This version checks
#      real_cost_pct_of_spot against MAX_PLAUSIBLE_COST_PCT_OF_SPOT (25%)
#      automatically, for every event, and flags/excludes anything over
#      that threshold from the summary stats -- while still keeping the
#      row (with a clear note) in the full results table for audit. 25% is
#      a generous threshold: the real, non-corrupted costs observed in the
#      first validation ranged 1.5%-12.0% of spot: even an extreme ~200%
#      annualized IV straddle over a 4-6 day hold works out to roughly
#      ~20% of spot under the Brenner-Subrahmanyam approximation, so 25%
#      gives headroom above any plausible real value while decisively
#      catching anything like the 719% corruption.
#
# Everything else (History<QuoteBar> pull, ATM strike selection, first
# expiration on/after exit_date, fee assumption, model-cost recompute) is
# UNCHANGED from the validated v1 methodology.
#
# HOW TO USE: paste this entire file's contents into an empty cell in your
# QuantConnect Research notebook (where `qb` is already available as
# QuantBook, or will be initialized below) and run it. No file upload
# required -- the sample is embedded.
# ============================================================================

import pandas as pd
import numpy as np
import math
from datetime import timedelta
from QuantConnect.Research import QuantBook

qb = QuantBook()

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
RISK_FREE_RATE = 0.02
NEAR_EARNINGS_IV_MARKUP = 1.2398   # ORIGINAL (uncorrected) markup -- this validation is what tests it
COST_LOADING = 1.05
VOL_LOOKBACK_TRADING_DAYS = 60
MIN_VOL_HISTORY_DAYS = 30

FEE_PER_CONTRACT_USD = 0.65
FEE_LEGS = 4
FEES_IN_QUOTE_UNITS = (FEE_PER_CONTRACT_USD * FEE_LEGS) / 100.0

MAX_PLAUSIBLE_COST_PCT_OF_SPOT = 25.0   # automated corruption filter -- see header note

TICKER_OVERRIDES = {"BRK-B": "BRK.B"}

# ---------------------------------------------------------------------------
# EMBEDDED STRATIFIED SAMPLE (n=90) -- ticker-proportional random sample,
# seed=7, from FixedWindow_PerEvent_Canonical.csv's 152-event population.
# All 27 tickers with qualifying events represented. NOT biased toward
# winners/losers -- pure proportional-random draw within each ticker.
# ---------------------------------------------------------------------------
EMBEDDED_SAMPLE = [
    {"ticker": "AAPL", "spike_week": "2022-10-23", "entry_date": "2022-10-25", "exit_date": "2022-10-28", "pnl_pct": -27.04, "win": False},
    {"ticker": "AAPL", "spike_week": "2023-04-30", "entry_date": "2023-05-02", "exit_date": "2023-05-05", "pnl_pct": 39.08, "win": True},
    {"ticker": "AAPL", "spike_week": "2025-01-26", "entry_date": "2025-01-28", "exit_date": "2025-01-31", "pnl_pct": -46.09, "win": False},
    {"ticker": "ABBV", "spike_week": "2024-10-27", "entry_date": "2024-10-29", "exit_date": "2024-11-01", "pnl_pct": 380.26, "win": True},
    {"ticker": "ADBE", "spike_week": "2021-03-21", "entry_date": "2021-03-23", "exit_date": "2021-03-26", "pnl_pct": -35.99, "win": False},
    {"ticker": "ADBE", "spike_week": "2021-09-19", "entry_date": "2021-09-21", "exit_date": "2021-09-24", "pnl_pct": 188.45, "win": True},
    {"ticker": "ADBE", "spike_week": "2021-12-12", "entry_date": "2021-12-14", "exit_date": "2021-12-17", "pnl_pct": 208.62, "win": True},
    {"ticker": "ADBE", "spike_week": "2022-09-11", "entry_date": "2022-09-13", "exit_date": "2022-09-16", "pnl_pct": 426.51, "win": True},
    {"ticker": "ADBE", "spike_week": "2023-03-12", "entry_date": "2023-03-14", "exit_date": "2023-03-17", "pnl_pct": 128.31, "win": True},
    {"ticker": "ADBE", "spike_week": "2023-12-10", "entry_date": "2023-12-12", "exit_date": "2023-12-15", "pnl_pct": 183.33, "win": True},
    {"ticker": "ADBE", "spike_week": "2025-03-09", "entry_date": "2025-03-11", "exit_date": "2025-03-14", "pnl_pct": 165.52, "win": True},
    {"ticker": "ADBE", "spike_week": "2025-12-07", "entry_date": "2025-12-09", "exit_date": "2025-12-12", "pnl_pct": 37.17, "win": True},
    {"ticker": "AMZN", "spike_week": "2022-10-23", "entry_date": "2022-10-25", "exit_date": "2022-10-28", "pnl_pct": 236.36, "win": True},
    {"ticker": "AMZN", "spike_week": "2023-01-29", "entry_date": "2023-01-31", "exit_date": "2023-02-03", "pnl_pct": -94.47, "win": False},
    {"ticker": "AMZN", "spike_week": "2023-07-30", "entry_date": "2023-08-01", "exit_date": "2023-08-04", "pnl_pct": 108.91, "win": True},
    {"ticker": "AMZN", "spike_week": "2024-04-28", "entry_date": "2024-04-30", "exit_date": "2024-05-03", "pnl_pct": 152.17, "win": True},
    {"ticker": "AMZN", "spike_week": "2024-07-28", "entry_date": "2024-07-30", "exit_date": "2024-08-02", "pnl_pct": 238.26, "win": True},
    {"ticker": "BKR", "spike_week": "2022-07-17", "entry_date": "2022-07-19", "exit_date": "2022-07-22", "pnl_pct": 232.92, "win": True},
    {"ticker": "BKR", "spike_week": "2025-07-20", "entry_date": "2025-07-22", "exit_date": "2025-07-25", "pnl_pct": 507.27, "win": True},
    {"ticker": "BRK-B", "spike_week": "2025-02-23", "entry_date": "2025-02-25", "exit_date": "2025-02-28", "pnl_pct": 103.57, "win": True},
    {"ticker": "COHR", "spike_week": "2024-02-04", "entry_date": "2024-02-06", "exit_date": "2024-02-09", "pnl_pct": 102.13, "win": True},
    {"ticker": "CTSH", "spike_week": "2022-10-30", "entry_date": "2022-11-01", "exit_date": "2022-11-04", "pnl_pct": 536.01, "win": True},
    {"ticker": "DELL", "spike_week": "2025-11-30", "entry_date": "2025-12-02", "exit_date": "2025-12-05", "pnl_pct": -53.91, "win": False},
    {"ticker": "DVN", "spike_week": "2023-02-12", "entry_date": "2023-02-14", "exit_date": "2023-02-17", "pnl_pct": 379.83, "win": True},
    {"ticker": "GME", "spike_week": "2024-03-24", "entry_date": "2024-03-26", "exit_date": "2024-03-28", "pnl_pct": 454.94, "win": True},
    {"ticker": "GME", "spike_week": "2025-09-07", "entry_date": "2025-09-09", "exit_date": "2025-09-12", "pnl_pct": 10.4, "win": True},
    {"ticker": "GOOGL", "spike_week": "2024-10-27", "entry_date": "2024-10-29", "exit_date": "2024-11-01", "pnl_pct": -55.22, "win": False},
    {"ticker": "GOOGL", "spike_week": "2025-10-26", "entry_date": "2025-10-28", "exit_date": "2025-10-31", "pnl_pct": 93.52, "win": True},
    {"ticker": "GPN", "spike_week": "2021-08-01", "entry_date": "2021-08-03", "exit_date": "2021-08-06", "pnl_pct": 104.05, "win": True},
    {"ticker": "GPN", "spike_week": "2024-08-04", "entry_date": "2024-08-06", "exit_date": "2024-08-09", "pnl_pct": 232.42, "win": True},
    {"ticker": "INTC", "spike_week": "2022-07-24", "entry_date": "2022-07-26", "exit_date": "2022-07-29", "pnl_pct": 96.02, "win": True},
    {"ticker": "INTC", "spike_week": "2024-01-21", "entry_date": "2024-01-23", "exit_date": "2024-01-26", "pnl_pct": 195.13, "win": True},
    {"ticker": "INTC", "spike_week": "2024-07-28", "entry_date": "2024-07-30", "exit_date": "2024-08-02", "pnl_pct": 761.31, "win": True},
    {"ticker": "INTC", "spike_week": "2025-07-20", "entry_date": "2025-07-22", "exit_date": "2025-07-25", "pnl_pct": 145.2, "win": True},
    {"ticker": "LDOS", "spike_week": "2021-08-01", "entry_date": "2021-08-03", "exit_date": "2021-08-06", "pnl_pct": -37.71, "win": False},
    {"ticker": "LDOS", "spike_week": "2023-04-30", "entry_date": "2023-05-02", "exit_date": "2023-05-05", "pnl_pct": -85.7, "win": False},
    {"ticker": "LDOS", "spike_week": "2024-02-11", "entry_date": "2024-02-13", "exit_date": "2024-02-16", "pnl_pct": 83.77, "win": True},
    {"ticker": "MSFT", "spike_week": "2022-01-23", "entry_date": "2022-01-25", "exit_date": "2022-01-28", "pnl_pct": 187.31, "win": True},
    {"ticker": "MSFT", "spike_week": "2022-07-24", "entry_date": "2022-07-26", "exit_date": "2022-07-29", "pnl_pct": 227.86, "win": True},
    {"ticker": "MSFT", "spike_week": "2022-10-23", "entry_date": "2022-10-25", "exit_date": "2022-10-28", "pnl_pct": 89.41, "win": True},
    {"ticker": "MSFT", "spike_week": "2023-01-22", "entry_date": "2023-01-24", "exit_date": "2023-01-27", "pnl_pct": -31.69, "win": False},
    {"ticker": "MSFT", "spike_week": "2023-04-23", "entry_date": "2023-04-25", "exit_date": "2023-04-28", "pnl_pct": 321.99, "win": True},
    {"ticker": "MSFT", "spike_week": "2024-07-28", "entry_date": "2024-07-30", "exit_date": "2024-08-02", "pnl_pct": 87.25, "win": True},
    {"ticker": "MSFT", "spike_week": "2024-10-27", "entry_date": "2024-10-29", "exit_date": "2024-11-01", "pnl_pct": 199.1, "win": True},
    {"ticker": "MSFT", "spike_week": "2025-01-26", "entry_date": "2025-01-28", "exit_date": "2025-01-31", "pnl_pct": 242.58, "win": True},
    {"ticker": "NCLH", "spike_week": "2025-11-02", "entry_date": "2025-11-04", "exit_date": "2025-11-07", "pnl_pct": -54.24, "win": False},
    {"ticker": "NFLX", "spike_week": "2021-07-18", "entry_date": "2021-07-20", "exit_date": "2021-07-23", "pnl_pct": 28.95, "win": True},
    {"ticker": "NFLX", "spike_week": "2021-10-17", "entry_date": "2021-10-19", "exit_date": "2021-10-22", "pnl_pct": 81.17, "win": True},
    {"ticker": "NFLX", "spike_week": "2022-04-17", "entry_date": "2022-04-19", "exit_date": "2022-04-22", "pnl_pct": 478.78, "win": True},
    {"ticker": "NFLX", "spike_week": "2022-10-16", "entry_date": "2022-10-18", "exit_date": "2022-10-21", "pnl_pct": 299.99, "win": True},
    {"ticker": "NFLX", "spike_week": "2023-01-15", "entry_date": "2023-01-17", "exit_date": "2023-01-20", "pnl_pct": -12.33, "win": False},
    {"ticker": "NFLX", "spike_week": "2023-07-16", "entry_date": "2023-07-18", "exit_date": "2023-07-21", "pnl_pct": 202.61, "win": True},
    {"ticker": "NFLX", "spike_week": "2024-07-14", "entry_date": "2024-07-16", "exit_date": "2024-07-19", "pnl_pct": 21.67, "win": True},
    {"ticker": "NFLX", "spike_week": "2024-10-13", "entry_date": "2024-10-15", "exit_date": "2024-10-18", "pnl_pct": 289.0, "win": True},
    {"ticker": "NFLX", "spike_week": "2025-01-19", "entry_date": "2025-01-21", "exit_date": "2025-01-24", "pnl_pct": 300.32, "win": True},
    {"ticker": "NKE", "spike_week": "2021-06-20", "entry_date": "2021-06-22", "exit_date": "2021-06-25", "pnl_pct": 620.29, "win": True},
    {"ticker": "NKE", "spike_week": "2022-03-20", "entry_date": "2022-03-22", "exit_date": "2022-03-25", "pnl_pct": -84.36, "win": False},
    {"ticker": "NKE", "spike_week": "2023-06-25", "entry_date": "2023-06-27", "exit_date": "2023-06-30", "pnl_pct": 12.01, "win": True},
    {"ticker": "NKE", "spike_week": "2023-09-24", "entry_date": "2023-09-26", "exit_date": "2023-09-29", "pnl_pct": 234.55, "win": True},
    {"ticker": "NKE", "spike_week": "2023-12-17", "entry_date": "2023-12-19", "exit_date": "2023-12-22", "pnl_pct": 371.67, "win": True},
    {"ticker": "NKE", "spike_week": "2024-03-17", "entry_date": "2024-03-19", "exit_date": "2024-03-22", "pnl_pct": 100.12, "win": True},
    {"ticker": "NKE", "spike_week": "2024-06-23", "entry_date": "2024-06-25", "exit_date": "2024-06-28", "pnl_pct": 808.41, "win": True},
    {"ticker": "NKE", "spike_week": "2025-09-28", "entry_date": "2025-09-30", "exit_date": "2025-10-03", "pnl_pct": -17.27, "win": False},
    {"ticker": "NVDA", "spike_week": "2022-02-13", "entry_date": "2022-02-15", "exit_date": "2022-02-18", "pnl_pct": 96.1, "win": True},
    {"ticker": "NVDA", "spike_week": "2022-05-22", "entry_date": "2022-05-24", "exit_date": "2022-05-27", "pnl_pct": 141.37, "win": True},
    {"ticker": "NVDA", "spike_week": "2023-05-21", "entry_date": "2023-05-23", "exit_date": "2023-05-26", "pnl_pct": 544.46, "win": True},
    {"ticker": "QCOM", "spike_week": "2021-10-31", "entry_date": "2021-11-02", "exit_date": "2021-11-05", "pnl_pct": 1093.0, "win": True},
    {"ticker": "QCOM", "spike_week": "2022-07-24", "entry_date": "2022-07-26", "exit_date": "2022-07-29", "pnl_pct": -31.73, "win": False},
    {"ticker": "QCOM", "spike_week": "2023-04-30", "entry_date": "2023-05-02", "exit_date": "2023-05-05", "pnl_pct": 146.51, "win": True},
    {"ticker": "QCOM", "spike_week": "2023-07-30", "entry_date": "2023-08-01", "exit_date": "2023-08-04", "pnl_pct": 145.84, "win": True},
    {"ticker": "QCOM", "spike_week": "2025-02-02", "entry_date": "2025-02-04", "exit_date": "2025-02-07", "pnl_pct": -2.05, "win": False},
    {"ticker": "QCOM", "spike_week": "2025-07-27", "entry_date": "2025-07-29", "exit_date": "2025-08-01", "pnl_pct": 184.81, "win": True},
    {"ticker": "SBUX", "spike_week": "2021-10-24", "entry_date": "2021-10-26", "exit_date": "2021-10-29", "pnl_pct": 374.58, "win": True},
    {"ticker": "SBUX", "spike_week": "2023-04-30", "entry_date": "2023-05-02", "exit_date": "2023-05-05", "pnl_pct": 250.37, "win": True},
    {"ticker": "SBUX", "spike_week": "2024-01-28", "entry_date": "2024-01-30", "exit_date": "2024-02-02", "pnl_pct": -53.11, "win": False},
    {"ticker": "SBUX", "spike_week": "2024-04-28", "entry_date": "2024-04-30", "exit_date": "2024-05-03", "pnl_pct": 966.94, "win": True},
    {"ticker": "SBUX", "spike_week": "2025-01-26", "entry_date": "2025-01-28", "exit_date": "2025-01-31", "pnl_pct": 269.64, "win": True},
    {"ticker": "SBUX", "spike_week": "2025-04-27", "entry_date": "2025-04-29", "exit_date": "2025-05-02", "pnl_pct": -95.83, "win": False},
    {"ticker": "STZ", "spike_week": "2023-01-01", "entry_date": "2022-12-30", "exit_date": "2023-01-06", "pnl_pct": 68.93, "win": True},
    {"ticker": "STZ", "spike_week": "2024-04-07", "entry_date": "2024-04-09", "exit_date": "2024-04-12", "pnl_pct": -82.5, "win": False},
    {"ticker": "SYK", "spike_week": "2023-01-29", "entry_date": "2023-01-31", "exit_date": "2023-02-03", "pnl_pct": 302.4, "win": True},
    {"ticker": "SYK", "spike_week": "2024-01-28", "entry_date": "2024-01-30", "exit_date": "2024-02-02", "pnl_pct": 362.07, "win": True},
    {"ticker": "SYK", "spike_week": "2024-04-28", "entry_date": "2024-04-30", "exit_date": "2024-05-03", "pnl_pct": 30.47, "win": True},
    {"ticker": "SYK", "spike_week": "2025-07-27", "entry_date": "2025-07-29", "exit_date": "2025-08-01", "pnl_pct": 297.24, "win": True},
    {"ticker": "TSLA", "spike_week": "2024-04-21", "entry_date": "2024-04-23", "exit_date": "2024-04-26", "pnl_pct": 254.74, "win": True},
    {"ticker": "TTWO", "spike_week": "2021-05-16", "entry_date": "2021-05-18", "exit_date": "2021-05-21", "pnl_pct": 280.39, "win": True},
    {"ticker": "TTWO", "spike_week": "2022-11-06", "entry_date": "2022-11-08", "exit_date": "2022-11-11", "pnl_pct": 154.7, "win": True},
    {"ticker": "TTWO", "spike_week": "2023-02-05", "entry_date": "2023-02-07", "exit_date": "2023-02-10", "pnl_pct": -41.08, "win": False},
    {"ticker": "TTWO", "spike_week": "2023-05-14", "entry_date": "2023-05-16", "exit_date": "2023-05-19", "pnl_pct": 296.44, "win": True},
    {"ticker": "UAL", "spike_week": "2021-07-18", "entry_date": "2021-07-20", "exit_date": "2021-07-23", "pnl_pct": -20.48, "win": False},
]

sample = pd.DataFrame(EMBEDDED_SAMPLE)
sample["spike_week"] = pd.to_datetime(sample["spike_week"])
sample["entry_date"] = pd.to_datetime(sample["entry_date"])
sample["exit_date"] = pd.to_datetime(sample["exit_date"])

print(f"Embedded stratified sample: n={len(sample)}  tickers={sample['ticker'].nunique()}  "
      f"(spans {sample['spike_week'].dt.year.min()}-{sample['spike_week'].dt.year.max()}, "
      f"{sample['win'].sum()} modeled wins / {len(sample)} total)")

# ---------------------------------------------------------------------------
# MODEL RECOMPUTE HELPERS
# ---------------------------------------------------------------------------
def norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs_straddle_price(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0:
        return None
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    call = S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
    put = K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)
    return call + put


def model_implied_cost_pct(equity_symbol, entry_date, exit_date):
    vol_start = entry_date - timedelta(days=VOL_LOOKBACK_TRADING_DAYS * 2 + 20)
    vol_end = entry_date - timedelta(days=1)
    px = qb.History(equity_symbol, vol_start, vol_end, Resolution.Daily)
    if px is None or px.empty or "close" not in px.columns:
        return None
    closes = px["close"].tail(VOL_LOOKBACK_TRADING_DAYS + 5)
    if len(closes) < MIN_VOL_HISTORY_DAYS:
        return None
    rets = closes.pct_change().dropna()
    sigma = float(rets.std() * math.sqrt(252))
    if sigma <= 0:
        return None
    iv = sigma * NEAR_EARNINGS_IV_MARKUP
    T = (exit_date - entry_date).days / 365.0
    fair = bs_straddle_price(100.0, 100.0, T, RISK_FREE_RATE, iv)
    if fair is None:
        return None
    return fair * COST_LOADING


def get_bid_ask(option_symbol, target_date):
    start = target_date - timedelta(days=5)
    end = target_date + timedelta(days=1)
    hist = qb.History(QuoteBar, option_symbol, start, end, Resolution.Minute)
    if hist is None or hist.empty:
        return None, None
    if isinstance(hist.index, pd.MultiIndex):
        times = hist.index.get_level_values(-1)
    else:
        times = hist.index
    mask = pd.to_datetime(times).date <= target_date.date()
    day_rows = hist[mask] if mask.any() else hist
    if day_rows.empty:
        return None, None
    last = day_rows.iloc[-1]
    bid = float(last["bidclose"]) if "bidclose" in last and pd.notna(last["bidclose"]) else None
    ask = float(last["askclose"]) if "askclose" in last and pd.notna(last["askclose"]) else None
    return bid, ask


# ---------------------------------------------------------------------------
# MAIN PER-EVENT LOOP
# ---------------------------------------------------------------------------
results = []

for idx, row in sample.iterrows():
    raw_ticker = row["ticker"]
    qc_ticker = TICKER_OVERRIDES.get(raw_ticker, raw_ticker)
    entry_date = row["entry_date"].to_pydatetime()
    exit_date = row["exit_date"].to_pydatetime()
    modeled_pnl_pct = float(row["pnl_pct"])
    modeled_win = bool(row["win"])

    rec = {"ticker": raw_ticker, "spike_week": row["spike_week"].date(),
           "entry_date": entry_date.date(), "exit_date": exit_date.date(),
           "modeled_pnl_pct": modeled_pnl_pct, "modeled_win": modeled_win,
           "corrupted": False, "note": ""}

    try:
        equity = qb.AddEquity(qc_ticker, Resolution.Daily)
        equity_symbol = equity.Symbol

        px_hist = qb.History(equity_symbol, entry_date - timedelta(days=7), entry_date + timedelta(days=1),
                              Resolution.Daily)
        if px_hist is None or px_hist.empty:
            rec["note"] = "no underlying price history at entry"
            results.append(rec); print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['spike_week'].date()}: {rec['note']}")
            continue
        entry_underlying_price = float(px_hist["close"].iloc[-1])
        rec["entry_underlying_price"] = entry_underlying_price

        contracts = list(qb.OptionChainProvider.GetOptionContractList(equity_symbol, entry_date))
        if not contracts:
            rec["note"] = "no option chain listed at entry date"
            results.append(rec); print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['spike_week'].date()}: {rec['note']}")
            continue

        expiries = sorted(set(c.ID.Date for c in contracts if c.ID.Date >= exit_date))
        if not expiries:
            rec["note"] = "no listed expiration on/after exit date"
            results.append(rec); print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['spike_week'].date()}: {rec['note']}")
            continue
        target_expiry = expiries[0]
        rec["expiry"] = target_expiry.date()

        same_expiry = [c for c in contracts if c.ID.Date == target_expiry]
        strikes = sorted(set(c.ID.StrikePrice for c in same_expiry))
        if not strikes:
            rec["note"] = "no strikes found for chosen expiration"
            results.append(rec); print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['spike_week'].date()}: {rec['note']}")
            continue
        atm_strike = min(strikes, key=lambda k: abs(k - entry_underlying_price))
        rec["strike"] = atm_strike

        call_symbol = next((c for c in same_expiry if c.ID.StrikePrice == atm_strike
                             and c.ID.OptionRight == OptionRight.Call), None)
        put_symbol = next((c for c in same_expiry if c.ID.StrikePrice == atm_strike
                            and c.ID.OptionRight == OptionRight.Put), None)
        if call_symbol is None or put_symbol is None:
            rec["note"] = "missing call or put contract at chosen strike/expiry"
            results.append(rec); print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['spike_week'].date()}: {rec['note']}")
            continue

        call_entry_bid, call_entry_ask = get_bid_ask(call_symbol, entry_date)
        put_entry_bid, put_entry_ask = get_bid_ask(put_symbol, entry_date)
        call_exit_bid, call_exit_ask = get_bid_ask(call_symbol, exit_date)
        put_exit_bid, put_exit_ask = get_bid_ask(put_symbol, exit_date)

        missing = [v is None for v in [call_entry_ask, put_entry_ask, call_exit_bid, put_exit_bid]]
        if any(missing):
            rec["note"] = "missing real quote data at entry or exit"
            results.append(rec); print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['spike_week'].date()}: {rec['note']}")
            continue

        entry_cost = call_entry_ask + put_entry_ask
        exit_value = call_exit_bid + put_exit_bid
        real_pnl_pct = (exit_value - entry_cost - FEES_IN_QUOTE_UNITS) / entry_cost * 100
        real_win = real_pnl_pct > 0

        real_cost_pct_of_spot = entry_cost / entry_underlying_price * 100

        # AUTOMATED CORRUPTION CHECK -- flag+exclude rather than requiring a
        # human to spot an implausible number after the fact (see header).
        if real_cost_pct_of_spot > MAX_PLAUSIBLE_COST_PCT_OF_SPOT:
            rec["corrupted"] = True
            rec["real_cost_pct_of_spot"] = round(real_cost_pct_of_spot, 3)
            rec["strike"] = atm_strike
            rec["note"] = (f"EXCLUDED: implausible real_cost_pct_of_spot="
                            f"{real_cost_pct_of_spot:.1f}% (> {MAX_PLAUSIBLE_COST_PCT_OF_SPOT}% threshold) "
                            f"-- likely a broken strike/expiry match, not a real quote")
            results.append(rec)
            print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['spike_week'].date()}: {rec['note']}")
            continue

        model_cost_pct = model_implied_cost_pct(equity_symbol, entry_date, exit_date)

        rec.update({
            "call_entry_ask": call_entry_ask, "put_entry_ask": put_entry_ask,
            "call_exit_bid": call_exit_bid, "put_exit_bid": put_exit_bid,
            "real_entry_cost": entry_cost, "real_exit_value": exit_value,
            "real_pnl_pct": round(real_pnl_pct, 2), "real_win": real_win,
            "model_implied_cost_pct": round(model_cost_pct, 3) if model_cost_pct is not None else None,
            "real_cost_pct_of_spot": round(real_cost_pct_of_spot, 3),
            "pricing_error_pct_points": round(real_cost_pct_of_spot - model_cost_pct, 3) if model_cost_pct is not None else None,
            "return_error_pct_points": round(real_pnl_pct - modeled_pnl_pct, 2),
            "win_match": real_win == modeled_win,
        })
        results.append(rec)
        print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['spike_week'].date()}: "
              f"real_pnl={real_pnl_pct:.1f}% modeled_pnl={modeled_pnl_pct:.1f}% "
              f"cost%spot={real_cost_pct_of_spot:.2f}% match={rec['win_match']}")

    except Exception as e:
        rec["note"] = f"exception: {e}"
        results.append(rec)
        print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['spike_week'].date()}: EXCEPTION: {e}")

results_df = pd.DataFrame(results)

# ---------------------------------------------------------------------------
# FINAL SUMMARY
# ---------------------------------------------------------------------------
n_corrupted = int(results_df["corrupted"].sum()) if "corrupted" in results_df.columns else 0
complete = results_df[(results_df.get("real_pnl_pct").notna()) & (~results_df["corrupted"])].copy() \
    if "real_pnl_pct" in results_df.columns else pd.DataFrame()

print("\n" + "=" * 70)
print("SUMMARY: real historical option quotes vs. modeled Black-Scholes prices (v2, expanded sample)")
print("=" * 70)
print(f"Sample size: {len(sample)}   Auto-flagged as corrupted: {n_corrupted}   "
      f"Successfully pulled + priced (clean): {len(complete)}   "
      f"Failed/incomplete (other reasons): {len(sample) - len(complete) - n_corrupted}")

if not complete.empty:
    median_pricing_error = complete["pricing_error_pct_points"].median()
    median_return_error = complete["return_error_pct_points"].median()
    real_win_rate = complete["real_win"].mean() * 100
    win_match_rate = complete["win_match"].mean() * 100

    print(f"\nWin rate (real, quote-derived): {real_win_rate:.1f}%")
    print(f"Median pricing error (real entry cost % of spot - modeled implied cost %): "
          f"{median_pricing_error:+.2f} pct points")
    print(f"Median return error (real pnl% - modeled pnl%): {median_return_error:+.2f} pct points")
    print(f"Win/loss classification match rate (real vs. modeled): {win_match_rate:.1f}%")

    summary_table = pd.DataFrame([{
        "n_sampled": len(sample),
        "n_corrupted_excluded": n_corrupted,
        "n_clean_priced": len(complete),
        "real_win_rate_pct": round(real_win_rate, 1),
        "median_pricing_error_pct_points": round(median_pricing_error, 3),
        "median_return_error_pct_points": round(median_return_error, 2),
        "win_loss_match_rate_pct": round(win_match_rate, 1),
    }])
else:
    print("\nNo events were successfully priced with real quotes -- check the 'note' "
          "column in results_df for why each event failed.")
    summary_table = pd.DataFrame([{
        "n_sampled": len(sample), "n_corrupted_excluded": n_corrupted, "n_clean_priced": 0,
        "real_win_rate_pct": None, "median_pricing_error_pct_points": None,
        "median_return_error_pct_points": None, "win_loss_match_rate_pct": None,
    }])

if n_corrupted > 0:
    print(f"\nAuto-flagged corrupted events (excluded from summary, kept in results_df for audit):")
    display(results_df[results_df["corrupted"] == True][["ticker", "spike_week", "real_cost_pct_of_spot", "note"]])

display(results_df)
display(summary_table)

# To export for local recalibration analysis (same format as the first validation):
# complete[["ticker","spike_week","real_cost_pct_of_spot","model_implied_cost_pct",
#           "real_pnl_pct","modeled_pnl_pct","real_win","modeled_win"]].to_csv(
#     "QC_Validation_CleanSample_v2.csv", index=False)
