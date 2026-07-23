#!/usr/bin/env python3
# TASK 1 — Multiverse analysis: test all 81 combinations of
#   rolling_window in {8, 12, 16 weeks}
#   x z_threshold  in {4, 5, 6}
#   x earnings_window in {3, 5, 7 days}
#   x exit_rule   in {spike_week, next_day, full_window}
#
# For each combination, the STRONG_EARNINGS event set is recomputed FRESH
# from AllTickers_ZscoreSeries.csv's raw 'gst' column (not the pre-baked
# zscore_simple column, which is fixed at window=12) and
# AllTickers_EarningsDates.csv. Pricing uses the same Black-Scholes
# straddle / calibrated near-earnings IV markup / 60-day trailing realized
# vol conventions used throughout this project (entry = anchor+2 days,
# fixed across all 81 combos — only exit_rule is varied per the task spec).
#
# exit_rule definitions:
#   spike_week : nearest trading day on/before anchor+6
#   full_window: nearest trading day on/before anchor+13
#   next_day   : next trading day after the matched earnings date (skipped
#                per-event if earnings date falls before entry — same
#                convention as the earlier Exit Optimization task)
#
# Output: Live Signal Engine/Multiverse_Analysis_Results.csv

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
from itertools import product
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

ZSCORE_PATH = Path("Live Signal Engine") / "AllTickers_ZscoreSeries.csv"
EARNINGS_PATH = Path("Live Signal Engine") / "AllTickers_EarningsDates.csv"
CALIBRATION_PATH = Path("Earnings Clustering Test") / "iv_calibration_buckets.csv"
OUT_PATH = Path("Live Signal Engine") / "Multiverse_Analysis_Results.csv"

ROLLING_WINDOWS = [8, 12, 16]
Z_THRESHOLDS = [4, 5, 6]
EARNINGS_WINDOWS = [3, 5, 7]
EXIT_RULES = ["spike_week", "next_day", "full_window"]
MIN_PERIODS = 8

ENTRY_OFFSET_DAYS = 2
RISK_FREE_RATE = 0.02
VOL_LOOKBACK_TRADING_DAYS = 60
MIN_VOL_HISTORY_DAYS = 30
COST_LOADING = 1.05
UNDERPOWERED_N = 20

# 2021-2025 study period boundaries (matches the canonical dataset elsewhere in this project)
STUDY_START = pd.Timestamp("2021-01-01")
STUDY_END = pd.Timestamp("2025-12-31")


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


def next_trading_day_after(daily, target):
    target = pd.Timestamp(target)
    eligible = daily.loc[daily["Date"] > target, "Date"]
    return eligible.min() if not eligible.empty else None


def cumulative_return(daily, ret_col, start_date, end_date):
    mask = (daily["Date"] > start_date) & (daily["Date"] <= end_date)
    rets = daily.loc[mask, ret_col]
    return float((1 + rets).prod() - 1) if not rets.empty else None


def trailing_realized_vol(daily, ret_col, cutoff):
    hist = daily.loc[daily["Date"] < cutoff].tail(VOL_LOOKBACK_TRADING_DAYS)
    if len(hist) < MIN_VOL_HISTORY_DAYS:
        return None
    return float(hist[ret_col].std() * math.sqrt(252))


def price_leg(daily, ret_col, entry_date, exit_date, sigma, markup):
    if exit_date is None or entry_date is None or exit_date <= entry_date:
        return None
    dte_days = (exit_date - entry_date).days
    if dte_days <= 0:
        return None
    T = dte_days / 365.0
    iv = sigma * markup
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


def main():
    print("*** TASK 1: Multiverse analysis -- 81 parameter combinations ***\n")

    near_earnings_markup = load_calibrated_near_earnings_markup()
    print(f"Calibrated near-earnings markup (reused): {near_earnings_markup:.4f}x\n")

    print("Loading foundation files...")
    zscore_raw = pd.read_csv(ZSCORE_PATH)
    zscore_raw["week"] = pd.to_datetime(zscore_raw["week"])
    earnings = pd.read_csv(EARNINGS_PATH)
    earnings["earnings_date"] = pd.to_datetime(earnings["earnings_date"])
    earnings_by_ticker = {t: g["earnings_date"].sort_values().reset_index(drop=True)
                          for t, g in earnings.groupby("ticker")}

    print("Precomputing z-score series for 3 rolling windows x 51 tickers...")
    z_cache = {}  # (ticker, window) -> DataFrame[week, gst, z]
    for ticker, g in zscore_raw.groupby("ticker"):
        g = g.sort_values("week").reset_index(drop=True)
        for w in ROLLING_WINDOWS:
            rolling = g["gst"].shift(1).rolling(window=w, min_periods=MIN_PERIODS)
            z = (g["gst"] - rolling.mean()) / rolling.std()
            z = z.replace([np.inf, -np.inf], np.nan)
            z_cache[(ticker, w)] = pd.DataFrame({"week": g["week"], "zscore": z})

    print("Loading daily price/return data for 51 tickers...")
    daily_cache = {t: load_daily_excess(t) for t in ALL_TICKERS}
    n_loaded = sum(1 for d in daily_cache.values() if not d.empty)
    print(f"  {n_loaded}/{len(ALL_TICKERS)} tickers loaded\n")

    def nearest_earnings_gap_and_date(ticker, anchor):
        hist = earnings_by_ticker.get(ticker)
        if hist is None or hist.empty:
            return None, None
        gaps = (hist - anchor).abs().dt.days
        idx = gaps.idxmin()
        return int(gaps.loc[idx]), hist.loc[idx]

    results = []
    combo_num = 0
    total_combos = len(ROLLING_WINDOWS) * len(Z_THRESHOLDS) * len(EARNINGS_WINDOWS) * len(EXIT_RULES)

    for rw, zt, ew in product(ROLLING_WINDOWS, Z_THRESHOLDS, EARNINGS_WINDOWS):
        # Build the STRONG_EARNINGS candidate event set once per (rw, zt, ew) —
        # identical across all 3 exit rules, since exit_rule doesn't affect
        # which events qualify, only how each qualifying event is priced.
        candidates = []
        for ticker in ALL_TICKERS:
            zdf = z_cache.get((ticker, rw))
            if zdf is None:
                continue
            hits = zdf[(zdf["zscore"] >= zt) & (zdf["week"] >= STUDY_START) & (zdf["week"] <= STUDY_END)]
            for _, r in hits.iterrows():
                gap, earn_date = nearest_earnings_gap_and_date(ticker, r["week"])
                if gap is None or gap > ew:
                    continue
                candidates.append({"ticker": ticker, "anchor": r["week"], "zscore": r["zscore"],
                                    "earnings_date": earn_date})

        for exit_rule in EXIT_RULES:
            combo_num += 1
            pnls = []
            for c in candidates:
                ticker, anchor = c["ticker"], c["anchor"]
                daily = daily_cache.get(ticker, pd.DataFrame())
                ret_col = f"{ticker} Daily Return"
                if daily.empty or ret_col not in daily.columns:
                    continue

                entry_date = nearest_trading_day_on_or_before(daily, anchor + timedelta(days=ENTRY_OFFSET_DAYS))
                if entry_date is None:
                    continue
                sigma = trailing_realized_vol(daily, ret_col, anchor - timedelta(days=7))
                if sigma is None:
                    continue

                if exit_rule == "spike_week":
                    exit_date = nearest_trading_day_on_or_before(daily, anchor + timedelta(days=6))
                elif exit_rule == "full_window":
                    exit_date = nearest_trading_day_on_or_before(daily, anchor + timedelta(days=13))
                else:  # next_day
                    earn_date = c["earnings_date"]
                    if earn_date is None or earn_date < entry_date:
                        continue
                    exit_date = next_trading_day_after(daily, earn_date)

                res = price_leg(daily, ret_col, entry_date, exit_date, sigma, near_earnings_markup)
                if res:
                    pnls.append(res["pnl_pct"])

            n = len(pnls)
            if n > 0:
                pnls_arr = np.array(pnls)
                win_rate = float((pnls_arr > 0).mean() * 100)
                median_pnl = float(np.median(pnls_arr))
                mean_pnl = float(pnls_arr.mean())
            else:
                win_rate = median_pnl = mean_pnl = None

            results.append({
                "rolling_window": rw, "z_threshold": zt, "earnings_window": ew, "exit_rule": exit_rule,
                "n_events": n, "underpowered": n < UNDERPOWERED_N,
                "win_rate_pct": round(win_rate, 1) if win_rate is not None else None,
                "median_pnl_pct": round(median_pnl, 1) if median_pnl is not None else None,
                "mean_pnl_pct": round(mean_pnl, 1) if mean_pnl is not None else None,
            })
            print(f"[{combo_num}/{total_combos}] rw={rw} z>={zt} ew={ew}d exit={exit_rule:11s} "
                  f"n={n:<4} win={win_rate if win_rate is not None else float('nan'):5.1f}% "
                  f"median={median_pnl if median_pnl is not None else float('nan'):+7.1f}%"
                  f"{'  [UNDERPOWERED]' if n < UNDERPOWERED_N else ''}")

    result_df = pd.DataFrame(results)
    result_df.to_csv(OUT_PATH, index=False)

    print(f"\n=== SUMMARY ({len(result_df)} combinations) ===")
    powered = result_df[result_df["n_events"] >= UNDERPOWERED_N]
    n_underpowered = int(result_df["underpowered"].sum())
    print(f"Underpowered (n<{UNDERPOWERED_N}): {n_underpowered}/{len(result_df)}")

    valid = powered.dropna(subset=["win_rate_pct", "median_pnl_pct"])
    frac_win_gt50 = (valid["win_rate_pct"] > 50).mean() * 100
    frac_median_pos = (valid["median_pnl_pct"] > 0).mean() * 100
    frac_both = ((valid["win_rate_pct"] > 50) & (valid["median_pnl_pct"] > 0)).mean() * 100
    print(f"Among {len(valid)} adequately-powered combinations:")
    print(f"  Fraction with win rate >50%:        {frac_win_gt50:.1f}%")
    print(f"  Fraction with positive median P&L:  {frac_median_pos:.1f}%")
    print(f"  Fraction with BOTH:                 {frac_both:.1f}%")

    print(f"\n=== PARAMETER SENSITIVITY (mean win rate / mean median P&L by level, powered combos only) ===")
    for param in ["rolling_window", "z_threshold", "earnings_window", "exit_rule"]:
        grp = valid.groupby(param).agg(mean_win=("win_rate_pct", "mean"),
                                        mean_median_pnl=("median_pnl_pct", "mean"),
                                        n_combos=("win_rate_pct", "count"))
        win_range = grp["mean_win"].max() - grp["mean_win"].min()
        pnl_range = grp["mean_median_pnl"].max() - grp["mean_median_pnl"].min()
        print(f"\n{param}: win-rate range across levels = {win_range:.1f}pt, median-P&L range = {pnl_range:.1f}pt")
        print(grp.round(1).to_string())

    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
