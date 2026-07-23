#!/usr/bin/env python3
# TASK 1 — Cross-sectional ranking: does RELATIVE attention within an
# earnings week (rank among that week's other earnings-reporting tickers)
# carry more information than ABSOLUTE attention (raw z>=5)?
#
# Uses the shared foundation (AllTickers_EarningsDates.csv,
# AllTickers_ZscoreSeries.csv — built once for this round of 3 tasks, not
# re-pulled here). For every week in 2021-2025, the "earnings-week cohort"
# = tickers with an earnings date within 5 days of that week's anchor.
# Within each week's cohort, tickers are ranked by that week's z-score
# (percentile rank). Weeks with cohort size < 4 can't support a meaningful
# quartile split and are excluded, counted, not silently dropped.
#   cross-sectional TOP:    percentile rank >= 0.75 within that week's cohort
#   cross-sectional BOTTOM: percentile rank <= 0.25 within that week's cohort
# Straddle P&L (spike_week horizon, entry anchor+2, exit anchor+6) is
# computed fresh here with the same earnings-aware pricing model used
# throughout this project (Black-Scholes, calibrated near-earnings IV
# markup) — these are NEW candidate events (cross-sectional top/bottom is
# a different selection rule than absolute z>=5, so many of them were
# never priced before).
#
# Output: Live Signal Engine/Task1_CrossSectionalRanking_Results.csv

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
OUT_PATH = Path("Live Signal Engine") / "Task1_CrossSectionalRanking_Results.csv"

EARNINGS_WINDOW_DAYS = 5
MIN_COHORT_SIZE = 4
TOP_PCT_THRESHOLD = 0.75
BOTTOM_PCT_THRESHOLD = 0.25
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
    print("*** TASK 1: Cross-sectional ranking within earnings weeks ***\n")

    near_earnings_markup = load_calibrated_near_earnings_markup()
    print(f"Calibrated near-earnings markup (reused): {near_earnings_markup:.4f}x\n")

    earnings_df = pd.read_csv(EARNINGS_PATH)
    earnings_df["earnings_date"] = pd.to_datetime(earnings_df["earnings_date"])
    earnings_by_ticker = {t: g["earnings_date"].tolist() for t, g in earnings_df.groupby("ticker")}

    z_df = pd.read_csv(ZSCORE_PATH)
    z_df["week"] = pd.to_datetime(z_df["week"])
    z_df = z_df.dropna(subset=["zscore_simple"])

    print(f"Loaded z-scores: {len(z_df)} (ticker, week) rows across {z_df['ticker'].nunique()} tickers")
    print(f"Loaded earnings dates for {len(earnings_by_ticker)} tickers\n")

    print("Building earnings-week cohorts and cross-sectional ranks...")
    all_weeks = sorted(z_df["week"].unique())
    cohort_rows = []
    n_weeks_too_small = 0
    for week in all_weeks:
        week_ts = pd.Timestamp(week)
        cohort_tickers = []
        for ticker, dates in earnings_by_ticker.items():
            if any(abs((d - week_ts).days) <= EARNINGS_WINDOW_DAYS for d in dates):
                cohort_tickers.append(ticker)
        if len(cohort_tickers) < MIN_COHORT_SIZE:
            if cohort_tickers:
                n_weeks_too_small += 1
            continue
        week_z = z_df[(z_df["week"] == week_ts) & (z_df["ticker"].isin(cohort_tickers))].copy()
        week_z = week_z.dropna(subset=["zscore_simple"])
        if len(week_z) < MIN_COHORT_SIZE:
            n_weeks_too_small += 1
            continue
        week_z["pct_rank"] = week_z["zscore_simple"].rank(pct=True)
        week_z["cohort_size"] = len(week_z)
        cohort_rows.append(week_z)

    cohorts = pd.concat(cohort_rows, ignore_index=True) if cohort_rows else pd.DataFrame()
    print(f"Weeks with cohort >= {MIN_COHORT_SIZE}: {len(cohort_rows)}   "
          f"weeks excluded (cohort exists but too small): {n_weeks_too_small}\n")

    cohorts["classification"] = np.select(
        [cohorts["pct_rank"] >= TOP_PCT_THRESHOLD, cohorts["pct_rank"] <= BOTTOM_PCT_THRESHOLD],
        ["cross_sectional_top", "cross_sectional_bottom"],
        default="middle",
    )

    top_events = cohorts[cohorts["classification"] == "cross_sectional_top"]
    bottom_events = cohorts[cohorts["classification"] == "cross_sectional_bottom"]
    print(f"Cross-sectional TOP events: n={len(top_events)}")
    print(f"Cross-sectional BOTTOM events: n={len(bottom_events)}\n")

    print("Pricing events (on-disk daily price data, earnings-aware model)...")
    daily_cache = {}
    for t in set(top_events["ticker"]) | set(bottom_events["ticker"]):
        daily_cache[t] = load_daily_excess(t)

    def price_group(df, label):
        rows = []
        for _, ev in df.iterrows():
            res = price_event(daily_cache, ev["ticker"], pd.Timestamp(ev["week"]), near_earnings_markup)
            if res is None:
                continue
            rows.append({"ticker": ev["ticker"], "week": ev["week"], "zscore": ev["zscore_simple"],
                         "pct_rank": ev["pct_rank"], "cohort_size": ev["cohort_size"],
                         "classification": label, "win": res["win"], "pnl_pct": res["pnl_pct"]})
        return pd.DataFrame(rows)

    top_priced = price_group(top_events, "cross_sectional_top")
    bottom_priced = price_group(bottom_events, "cross_sectional_bottom")

    all_priced = pd.concat([top_priced, bottom_priced], ignore_index=True)
    all_priced.to_csv(OUT_PATH, index=False)

    print(f"\nPriced TOP: n={len(top_priced)}   Priced BOTTOM: n={len(bottom_priced)}\n")

    print(f"=== RESULTS (spike_week horizon) ===")
    print(f"Absolute z>=5 baseline:        n=147  win={BASELINE_WIN_PCT}%  median={BASELINE_MEDIAN_PCT:+.1f}%")
    if len(top_priced):
        print(f"Cross-sectional TOP (>=75th):  n={len(top_priced):<4} win={top_priced['win'].mean()*100:5.1f}%  "
              f"avg={top_priced['pnl_pct'].mean():+7.1f}%  median={top_priced['pnl_pct'].median():+7.1f}%")
    if len(bottom_priced):
        print(f"Cross-sectional BOTTOM (<=25th): n={len(bottom_priced):<4} win={bottom_priced['win'].mean()*100:5.1f}%  "
              f"avg={bottom_priced['pnl_pct'].mean():+7.1f}%  median={bottom_priced['pnl_pct'].median():+7.1f}%")

    if len(top_priced) and len(bottom_priced):
        rng = np.random.default_rng(RANDOM_SEED)
        diff, p = two_sample_permutation_test(
            top_priced["pnl_pct"].to_numpy(dtype=float), bottom_priced["pnl_pct"].to_numpy(dtype=float),
            N_PERMUTATIONS, rng)
        sig = "significant" if p < 0.05 else "not significant"
        print(f"\nDiff (TOP - BOTTOM): {diff:+.1f}pt  p={p:.4f} ({sig})")

    # overlap with absolute z>=5
    n_top_also_abs5 = (top_priced["zscore"] >= 5).sum() if len(top_priced) else 0
    print(f"\nOf the cross-sectional TOP events, {n_top_also_abs5}/{len(top_priced)} also clear absolute z>=5.")

    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
