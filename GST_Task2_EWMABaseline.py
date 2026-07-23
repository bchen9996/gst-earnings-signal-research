#!/usr/bin/env python3
# TASK 2 — Dynamic baseline (EWMA): recompute z-scores using an
# exponentially weighted mean/std (halflife=6 weeks, comparable center of
# mass to the current 12-week simple rolling window) instead of a simple
# rolling mean/std. Point-in-time discipline preserved identically
# (shift(1) before the ewm, so the current week never leaks into its own
# baseline — same guarantee as the production z-score).
#
# Uses the shared foundation (AllTickers_EarningsDates.csv,
# AllTickers_ZscoreSeries.csv, which already has zscore_ewma computed
# alongside zscore_simple). EWMA-z>=5 AND near_earnings (within 5 days of
# an actual earnings date, using the comprehensive 51-ticker earnings
# calendar — not the old previously-sampled-anchors-only flags files)
# defines "EWMA STRONG_EARNINGS." Reclassification (retained/lost/gained)
# compared against the original simple-rolling z>=5 STRONG_EARNINGS set.
# Straddle P&L priced fresh (same earnings-aware model) since EWMA
# flags a different set of weeks than the simple rolling window.
#
# Output: Live Signal Engine/Task2_EWMABaseline_Results.csv

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import sys
import math
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

TICKERS_ORIGINAL = [
    "TSLA", "NVDA", "AAPL", "MSFT", "AMZN",
    "GOOGL", "NFLX", "ADBE", "NKE", "SBUX",
    "INTC", "TTWO", "QCOM", "GME", "EBAY",
]
TICKERS_BROAD50_CLEAR = [
    'ABBV', 'ADP', 'ALB', 'ALLE', 'AVB', 'BKR', 'BRK-B', 'CCL', 'COF', 'COHR',
    'CTSH', 'CTVA', 'DELL', 'DVN', 'ERIE', 'GPC', 'GPN', 'JBL', 'LDOS', 'LNT',
    'MCHP', 'MCK', 'MDT', 'NCLH', 'PKG', 'PLD', 'PNW', 'RCL', 'REG', 'ROP',
    'RTX', 'STZ', 'SYF', 'SYK', 'UAL', 'XOM',
]
ALL_TICKERS = TICKERS_ORIGINAL + TICKERS_BROAD50_CLEAR
YEARS = list(range(2021, 2026))

DAILY_DIRS = {t: Path("Daily Excess Return Data (2021-2025)") for t in TICKERS_ORIGINAL}
DAILY_DIRS.update({t: Path("Daily Excess Return Data (2021-2025 Broad50 Clear)") for t in TICKERS_BROAD50_CLEAR})

EARNINGS_PATH = Path("Live Signal Engine") / "AllTickers_EarningsDates.csv"
ZSCORE_PATH = Path("Live Signal Engine") / "AllTickers_ZscoreSeries.csv"
CALIBRATION_PATH = Path("Earnings Clustering Test") / "iv_calibration_buckets.csv"
GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
OUT_PATH = Path("Live Signal Engine") / "Task2_EWMABaseline_Results.csv"

Z_THRESHOLD = 5.0
EARNINGS_WINDOW_DAYS = 5
ENTRY_OFFSET_DAYS = 2
EXIT_OFFSET_DAYS = 6
RISK_FREE_RATE = 0.02
VOL_LOOKBACK_TRADING_DAYS = 60
MIN_VOL_HISTORY_DAYS = 30
COST_LOADING = 1.05
N_PERMUTATIONS = 10000
RANDOM_SEED = 42

BASELINE_WIN_PCT = 76.2
BASELINE_MEDIAN_PCT = 130.0


def load_calibrated_near_earnings_markup() -> float:
    df = pd.read_csv(CALIBRATION_PATH, index_col=0)
    near_row = df[df.index.str.startswith("near earnings")]
    return float(near_row["mean"].iloc[0])


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


def load_daily_excess(ticker: str) -> pd.DataFrame:
    frames = []
    for year in YEARS:
        p = DAILY_DIRS[ticker] / f"{ticker}_{year}_excess.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        if "Date" not in df.columns:
            continue
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        frames.append(df.dropna(subset=["Date"]))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values("Date").reset_index(drop=True)


def nearest_trading_day_on_or_before(daily, target):
    target = pd.Timestamp(target)
    eligible = daily.loc[daily["Date"] <= target, "Date"]
    return eligible.max() if not eligible.empty else None


def cumulative_return(daily, ret_col, start_date, end_date):
    mask = (daily["Date"] > start_date) & (daily["Date"] <= end_date)
    rets = daily.loc[mask, ret_col]
    return float((1 + rets).prod() - 1) if not rets.empty else None


def trailing_realized_vol(daily, ret_col, cutoff):
    hist = daily.loc[daily["Date"] < cutoff].tail(VOL_LOOKBACK_TRADING_DAYS)
    if len(hist) < MIN_VOL_HISTORY_DAYS:
        return None
    return float(hist[ret_col].std() * math.sqrt(252))


def price_event(daily_cache, ticker, anchor, sigma_markup):
    daily = daily_cache.get(ticker)
    ret_col = f"{ticker} Daily Return"
    if daily is None or daily.empty or ret_col not in daily.columns:
        return None
    entry_date = nearest_trading_day_on_or_before(daily, anchor + timedelta(days=ENTRY_OFFSET_DAYS))
    if entry_date is None:
        return None
    exit_date = nearest_trading_day_on_or_before(daily, anchor + timedelta(days=EXIT_OFFSET_DAYS))
    if exit_date is None or exit_date <= entry_date:
        return None
    dte_days = (exit_date - entry_date).days
    if dte_days <= 0:
        return None
    sigma = trailing_realized_vol(daily, ret_col, anchor - timedelta(days=7))
    if sigma is None:
        return None
    T = dte_days / 365.0
    iv = sigma * sigma_markup
    fair = bs_straddle_price(100.0, 100.0, T, RISK_FREE_RATE, iv)
    if fair is None:
        return None
    cost = fair * COST_LOADING
    cum_ret = cumulative_return(daily, ret_col, entry_date, exit_date)
    if cum_ret is None:
        return None
    intrinsic = abs(100.0 * (1 + cum_ret) - 100.0)
    pnl_pct = (intrinsic - cost) / cost * 100
    return {"win": pnl_pct > 0, "pnl_pct": pnl_pct}


def two_sample_permutation_test(a, b, n_perm, rng):
    a = a[~np.isnan(a)]; b = b[~np.isnan(b)]
    if len(a) == 0 or len(b) == 0:
        return None, None
    observed_diff = a.mean() - b.mean()
    pooled = np.concatenate([a, b]); n_a = len(a)
    count = 0
    for _ in range(n_perm):
        rng.shuffle(pooled)
        d = pooled[:n_a].mean() - pooled[n_a:].mean()
        if abs(d) >= abs(observed_diff):
            count += 1
    return observed_diff, count / n_perm


def main():
    print(f"*** TASK 2: EWMA dynamic baseline (halflife=6wk) vs simple-rolling z>={Z_THRESHOLD:g} ***\n")

    near_earnings_markup = load_calibrated_near_earnings_markup()
    print(f"Calibrated near-earnings markup (reused): {near_earnings_markup:.4f}x\n")

    earnings_df = pd.read_csv(EARNINGS_PATH)
    earnings_df["earnings_date"] = pd.to_datetime(earnings_df["earnings_date"])
    earnings_by_ticker = {t: g["earnings_date"].tolist() for t, g in earnings_df.groupby("ticker")}

    z_df = pd.read_csv(ZSCORE_PATH)
    z_df["week"] = pd.to_datetime(z_df["week"])

    def near_earnings(ticker, week):
        dates = earnings_by_ticker.get(ticker, [])
        return any(abs((d - week).days) <= EARNINGS_WINDOW_DAYS for d in dates)

    ewma_candidates = z_df.dropna(subset=["zscore_ewma"])
    ewma_candidates = ewma_candidates[ewma_candidates["zscore_ewma"] >= Z_THRESHOLD].copy()
    ewma_candidates["near_earnings"] = [near_earnings(t, w) for t, w in
                                         zip(ewma_candidates["ticker"], ewma_candidates["week"])]
    ewma_strong = ewma_candidates[ewma_candidates["near_earnings"]]
    print(f"EWMA-z>={Z_THRESHOLD:g} candidates: n={len(ewma_candidates)}   "
          f"EWMA STRONG_EARNINGS (also near_earnings): n={len(ewma_strong)}\n")

    original = pd.read_csv(GROUP_A_PATH)
    original = original[original["zscore"] >= Z_THRESHOLD].copy()
    original["spike_week"] = pd.to_datetime(original["spike_week"])
    original_keys = set(zip(original["ticker"], original["spike_week"]))
    ewma_keys = set(zip(ewma_strong["ticker"], ewma_strong["week"]))

    retained = original_keys & ewma_keys
    lost = original_keys - ewma_keys
    gained = ewma_keys - original_keys
    print(f"=== RECLASSIFICATION vs original simple-rolling z>={Z_THRESHOLD:g} STRONG_EARNINGS (n={len(original_keys)}) ===")
    print(f"Retained (both methods flag it): {len(retained)}")
    print(f"Lost (simple flagged, EWMA does NOT): {len(lost)}")
    print(f"Gained (EWMA flags, simple did NOT): {len(gained)}\n")

    print("Pricing full EWMA STRONG_EARNINGS set (on-disk daily price data, earnings-aware model)...")
    daily_cache = {t: load_daily_excess(t) for t in ewma_strong["ticker"].unique()}
    rows = []
    for _, ev in ewma_strong.iterrows():
        res = price_event(daily_cache, ev["ticker"], ev["week"], near_earnings_markup)
        if res is None:
            continue
        rows.append({"ticker": ev["ticker"], "week": ev["week"], "zscore_ewma": ev["zscore_ewma"],
                     "retained_from_simple": (ev["ticker"], ev["week"]) in original_keys,
                     "win": res["win"], "pnl_pct": res["pnl_pct"]})
    priced = pd.DataFrame(rows)
    priced.to_csv(OUT_PATH, index=False)

    print(f"\nUsable priced EWMA STRONG_EARNINGS events: n={len(priced)}\n")
    print(f"=== RESULTS (spike_week horizon) ===")
    print(f"Original simple-rolling z>={Z_THRESHOLD:g} baseline: n=147  win={BASELINE_WIN_PCT}%  median={BASELINE_MEDIAN_PCT:+.1f}%")
    if len(priced):
        wr = priced["win"].mean() * 100
        avg = priced["pnl_pct"].mean()
        med = priced["pnl_pct"].median()
        print(f"EWMA STRONG_EARNINGS:                n={len(priced):<4} win={wr:5.1f}%  avg={avg:+7.1f}%  median={med:+7.1f}%")

        rng = np.random.default_rng(RANDOM_SEED)
        orig_pnl = original["end_of_spike_week_pnl_pct"].dropna().to_numpy(dtype=float)
        diff, p = two_sample_permutation_test(priced["pnl_pct"].to_numpy(dtype=float), orig_pnl, N_PERMUTATIONS, rng)
        sig = "significant" if p < 0.05 else "not significant"
        print(f"\nDiff (EWMA - simple-rolling original), P&L: {diff:+.1f}pt  p={p:.4f} ({sig})")

    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
