#!/usr/bin/env python3
# TASK 5 — Bollinger Band width as a signal quality filter: does a
# COMPRESSED volatility regime right before a STRONG_EARNINGS (z>=5) spike
# predict a bigger subsequent move ("coiled spring" hypothesis)? All
# on-disk data, no new pulls.
#
# No raw price LEVEL series exists on disk (only daily returns) — a
# synthetic price series is reconstructed per ticker by compounding its
# own daily return column from an arbitrary base of 100. This is valid for
# Bollinger %-width specifically: width = (upper-lower)/SMA = 4*STD/SMA is
# a RATIO, invariant to the arbitrary rebasing constant, so the synthetic
# series produces the same %-width a real price series would.
#
# BB width (20-day SMA/STD, 2 std dev) is computed for EVERY trading day
# across each ticker's full 2021-2025 synthetic series, then:
#   - the event's own pre-spike width = the value on the last trading day
#     BEFORE the anchor (no look-ahead into the spike week itself)
#   - "that ticker's median BB width" = the median of the ticker's FULL
#     width series (not just at event dates), giving a genuine per-ticker
#     baseline to compare against
#   compressed: event's pre-spike width <  ticker's own median width
#   expanded:   event's pre-spike width >= ticker's own median width
#
# Straddle P&L (spike_week horizon) reused as-is from the existing Group A
# file, not recomputed.
#
# Output: Live Signal Engine/Task5_BollingerBandWidth_Results.csv

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
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

DAILY_DIRS = {t: Path("Daily Excess Return Data (2021-2025)") for t in TICKERS_ORIGINAL}
DAILY_DIRS.update({t: Path("Daily Excess Return Data (2021-2025 Broad50 Clear)") for t in TICKERS_BROAD50_CLEAR})

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
OUT_PATH = Path("Live Signal Engine") / "Task5_BollingerBandWidth_Results.csv"

Z_THRESHOLD = 5.0
BB_WINDOW = 20
BB_STD_MULT = 2
N_PERMUTATIONS = 10000
RANDOM_SEED = 42


def load_daily(ticker: str) -> pd.DataFrame:
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


def compute_bb_width_series(daily: pd.DataFrame, ret_col: str) -> pd.DataFrame:
    df = daily[["Date", ret_col]].dropna().copy()
    df["synthetic_price"] = 100.0 * (1 + df[ret_col]).cumprod()
    sma = df["synthetic_price"].rolling(BB_WINDOW).mean()
    std = df["synthetic_price"].rolling(BB_WINDOW).std()
    df["bb_width"] = (BB_STD_MULT * 2 * std) / sma
    return df.dropna(subset=["bb_width"])[["Date", "bb_width"]]


def two_sample_permutation_test(a: np.ndarray, b: np.ndarray, n_perm: int, rng: np.random.Generator):
    a = a[~np.isnan(a)]
    b = b[~np.isnan(b)]
    if len(a) == 0 or len(b) == 0:
        return None, None, None, None
    observed_diff = a.mean() - b.mean()
    pooled = np.concatenate([a, b])
    n_a = len(a)
    count = 0
    for _ in range(n_perm):
        rng.shuffle(pooled)
        diff = pooled[:n_a].mean() - pooled[n_a:].mean()
        if abs(diff) >= abs(observed_diff):
            count += 1
    return observed_diff, count / n_perm, a.mean(), b.mean()


def main():
    print(f"*** TASK 5: Bollinger Band width (z>={Z_THRESHOLD:g}) ***\n")

    events = pd.read_csv(GROUP_A_PATH)
    events = events[events["zscore"] >= Z_THRESHOLD].copy()
    events["spike_week"] = pd.to_datetime(events["spike_week"])
    tickers = sorted(events["ticker"].unique())
    print(f"z>={Z_THRESHOLD:g} STRONG_EARNINGS events: n={len(events)} across {len(tickers)} tickers\n")

    print("Building BB width series per ticker (on-disk data)...")
    bb_cache: dict[str, pd.DataFrame] = {}
    ticker_median: dict[str, float] = {}
    for ticker in tickers:
        daily = load_daily(ticker)
        ret_col = f"{ticker} Daily Return"
        if daily.empty or ret_col not in daily.columns:
            continue
        bb_series = compute_bb_width_series(daily, ret_col)
        if bb_series.empty:
            continue
        bb_cache[ticker] = bb_series
        ticker_median[ticker] = float(bb_series["bb_width"].median())
    print(f"Built BB width series for {len(bb_cache)} tickers.\n")

    rows = []
    n_excluded = 0
    for _, ev in events.iterrows():
        ticker, anchor = ev["ticker"], ev["spike_week"]
        bb_series = bb_cache.get(ticker)
        if bb_series is None:
            n_excluded += 1
            continue
        prior = bb_series.loc[bb_series["Date"] < anchor]
        if prior.empty:
            n_excluded += 1
            continue
        event_width = float(prior.iloc[-1]["bb_width"])
        median_width = ticker_median[ticker]
        regime = "compressed" if event_width < median_width else "expanded"

        rows.append({
            "ticker": ticker, "spike_week": anchor.date(), "zscore": ev["zscore"],
            "pre_spike_bb_width": round(event_width, 4), "ticker_median_bb_width": round(median_width, 4),
            "regime": regime,
            "end_of_spike_week_win": ev["end_of_spike_week_win"],
            "end_of_spike_week_pnl_pct": ev["end_of_spike_week_pnl_pct"],
        })

    if n_excluded:
        print(f"NOTE: {n_excluded} event(s) excluded — insufficient price history for a full 20-day BB window "
              f"before the anchor.\n")

    result = pd.DataFrame(rows)
    result.to_csv(OUT_PATH, index=False)

    win_col, pnl_col = "end_of_spike_week_win", "end_of_spike_week_pnl_pct"
    compressed = result[result["regime"] == "compressed"]
    expanded = result[result["regime"] == "expanded"]
    comp_u = compressed[compressed[win_col].notna()]
    exp_u = expanded[expanded[win_col].notna()]

    print(f"=== COMPRESSED (pre-spike BB width < ticker's own median), n={len(comp_u)} ===")
    print(f"win={comp_u[win_col].mean()*100:.1f}%  avg={comp_u[pnl_col].mean():+.1f}%  median={comp_u[pnl_col].median():+.1f}%")
    print(f"=== EXPANDED (pre-spike BB width >= ticker's own median), n={len(exp_u)} ===")
    print(f"win={exp_u[win_col].mean()*100:.1f}%  avg={exp_u[pnl_col].mean():+.1f}%  median={exp_u[pnl_col].median():+.1f}%")

    if len(comp_u) and len(exp_u):
        rng = np.random.default_rng(RANDOM_SEED)
        diff, p, c_mean, e_mean = two_sample_permutation_test(
            comp_u[pnl_col].to_numpy(dtype=float), exp_u[pnl_col].to_numpy(dtype=float), N_PERMUTATIONS, rng)
        sig = "significant" if p < 0.05 else "not significant"
        print(f"\nDiff (Compressed - Expanded): {diff:+.1f} pts   two-sided p={p:.4f} ({sig})")
        if p < 0.05 and diff > 0:
            print("=> Compressed volatility + GST spike DOES predict a bigger subsequent move — hypothesis supported.")
        else:
            print("=> Hypothesis NOT supported by this data.")

    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
