#!/usr/bin/env python3
# TASK 2 — Ticker-specific historical percentile thresholds vs the fixed
# z>=5 cutoff. All on-disk data, no new pulls.
#
# Recomputes the FULL weekly z-score series per ticker (all ~260 weeks per
# ticker across 2021-2025, not just the weeks that already cleared z>=2)
# from the raw GST Data/Weekly Data (2021-2025)*/​<TICKER>_<YEAR>.csv files,
# using the exact same rolling methodology as the production engine
# (shift(1).rolling(window=12, min_periods=8)). From that FULL
# distribution, computes each ticker's own 90th/95th/99th/99.5th
# percentile z-score. Candidate events (near_earnings=True spikes) come
# from Straddle Profitability Test (2021-2025 51Ticker)/results.csv,
# reusing its already-computed earnings-aware P&L — not re-priced.
#
# *** COVERAGE CAVEAT — DISCLOSED ***
# results.csv only contains z>=4 events (that was the base filter of the
# whole straddle-simulation pipeline; the zconjunction files it draws from
# only ever recorded z>=2 spikes in the first place, and z>=4 was applied
# on top). For any ticker whose own percentile cutoff falls BELOW 4.0
# (relevant mainly at the 90th/95th percentile for less-volatile tickers),
# some genuinely-qualifying weeks are NOT present in results.csv and can't
# be counted — those tickers are flagged per threshold, not silently
# undercounted without notice.
#
# Output: Live Signal Engine/Task2_PercentileThresholds_Results.csv

from __future__ import annotations
from pathlib import Path
import sys
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

WEEKLY_DIRS = {t: Path("GST Data/Weekly Data (2021-2025)") for t in TICKERS_ORIGINAL}
WEEKLY_DIRS.update({t: Path("GST Data/Weekly Data (2021-2025 Broad50 Clear)") for t in TICKERS_BROAD50_CLEAR})

RESULTS_PATH = Path("Straddle Profitability Test (2021-2025 51Ticker)") / "results.csv"
OUT_PATH = Path("Live Signal Engine") / "Task2_PercentileThresholds_Results.csv"

ROLLING_WINDOW = 12
MIN_PERIODS = 8
PERCENTILES = [90, 95, 99, 99.5]
CURRENT_Z_THRESHOLD = 5.0
HORIZON = "end_of_spike_week"


def load_full_weekly_series(ticker: str) -> pd.DataFrame:
    frames = []
    for year in YEARS:
        p = WEEKLY_DIRS[ticker] / f"{ticker}_{year}.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        if "Week" not in df.columns or ticker not in df.columns:
            continue
        df = df.rename(columns={ticker: "gst"})[["Week", "gst"]]
        df["Week"] = pd.to_datetime(df["Week"], errors="coerce")
        frames.append(df.dropna(subset=["Week"]))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values("Week").reset_index(drop=True)


def compute_full_zscore_series(df: pd.DataFrame) -> pd.Series:
    rolling = df["gst"].shift(1).rolling(window=ROLLING_WINDOW, min_periods=MIN_PERIODS)
    roll_mean = rolling.mean()
    roll_std = rolling.std()
    z = (df["gst"] - roll_mean) / roll_std
    return z.replace([np.inf, -np.inf], np.nan).dropna()


def main():
    print("*** TASK 2: Ticker-specific historical percentile thresholds ***\n")

    print("Recomputing full weekly z-score history per ticker (on-disk raw GST data)...")
    ticker_percentiles = {}
    for ticker in ALL_TICKERS:
        weekly = load_full_weekly_series(ticker)
        if weekly.empty:
            print(f"  [{ticker}] no weekly data found, skipping")
            continue
        z_series = compute_full_zscore_series(weekly)
        if len(z_series) < 20:
            print(f"  [{ticker}] insufficient z-score history ({len(z_series)} weeks), skipping")
            continue
        ticker_percentiles[ticker] = {p: np.percentile(z_series, p) for p in PERCENTILES}
    print(f"Computed percentile thresholds for {len(ticker_percentiles)}/{len(ALL_TICKERS)} tickers.\n")

    results = pd.read_csv(RESULTS_PATH)
    results["spike_week"] = pd.to_datetime(results["spike_week"])
    win_col, pnl_col = f"{HORIZON}_win", f"{HORIZON}_pnl_pct"

    # Baseline: current fixed z>=5 threshold, near_earnings=True (matches the established headline)
    baseline = results[(results["zscore"] >= CURRENT_Z_THRESHOLD) & (results["near_earnings"] == True)]  # noqa: E712
    baseline_usable = baseline[baseline[win_col].notna()]
    print(f"BASELINE (fixed z>=5, near_earnings=True): n={len(baseline_usable)}  "
          f"win={baseline_usable[win_col].mean()*100:.1f}%  median={baseline_usable[pnl_col].median():+.1f}%\n")

    rows = [{
        "method": "fixed_z>=5", "n": len(baseline_usable),
        "win_rate_pct": round(baseline_usable[win_col].mean() * 100, 1),
        "median_pnl_pct": round(baseline_usable[pnl_col].median(), 1),
        "avg_pnl_pct": round(baseline_usable[pnl_col].mean(), 1),
        "n_tickers_cutoff_below_4": None, "note": "current live threshold, for comparison",
    }]

    for p in PERCENTILES:
        below_4_tickers = []
        qualifying_rows = []
        for _, ev in results.iterrows():
            ticker = ev["ticker"]
            if ticker not in ticker_percentiles or not ev["near_earnings"]:
                continue
            cutoff = ticker_percentiles[ticker][p]
            if ev["zscore"] >= cutoff:
                qualifying_rows.append(ev)

        for ticker, pct_map in ticker_percentiles.items():
            if pct_map[p] < 4.0:
                below_4_tickers.append(ticker)

        sub = pd.DataFrame(qualifying_rows)
        usable = sub[sub[win_col].notna()] if len(sub) else sub
        n = len(usable)
        if n == 0:
            print(f"{p}th percentile: no usable events")
            rows.append({"method": f"percentile_{p}", "n": 0, "win_rate_pct": None, "median_pnl_pct": None,
                         "avg_pnl_pct": None, "n_tickers_cutoff_below_4": len(below_4_tickers),
                         "note": f"tickers w/ cutoff<4.0 (possible undercount): {below_4_tickers}"})
            continue

        wr = usable[win_col].mean() * 100
        med = usable[pnl_col].median()
        avg = usable[pnl_col].mean()
        note = f"tickers w/ cutoff<4.0 (possible undercount): {below_4_tickers}" if below_4_tickers else "full coverage, no undercount risk"
        print(f"{p}th percentile: n={n:<4} win={wr:5.1f}%  avg={avg:+7.1f}%  median={med:+7.1f}%   "
              f"[{len(below_4_tickers)} ticker(s) with cutoff<4.0]")

        rows.append({
            "method": f"percentile_{p}", "n": n, "win_rate_pct": round(wr, 1),
            "median_pnl_pct": round(med, 1), "avg_pnl_pct": round(avg, 1),
            "n_tickers_cutoff_below_4": len(below_4_tickers), "note": note,
        })

    result_df = pd.DataFrame(rows)
    result_df.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
