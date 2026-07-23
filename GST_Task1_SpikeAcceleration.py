#!/usr/bin/env python3
# TASK 1 — Spike acceleration: does it matter whether attention is still
# BUILDING (delta_z > 0) vs already PEAKED (delta_z <= 0) the week a
# STRONG_EARNINGS (z>=5) event fires? All on-disk data, no new pulls.
#
# Recomputes the FULL weekly z-score series per ticker (same methodology
# as the production engine and the earlier percentile-threshold task) from
# the raw GST Data/Weekly Data (2021-2025)*/ files, then for each z>=5
# event looks up that week's z-score AND the immediately prior week's
# z-score (GST weeks are Sunday-anchored, confirmed in this project — the
# "prior week" is anchor - 7 days) to compute delta_z. Straddle P&L
# (spike_week horizon) reused as-is from the existing Group A file, not
# recomputed.
#
# Output: Live Signal Engine/Task1_SpikeAcceleration_Results.csv

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

WEEKLY_DIRS = {t: Path("GST Data/Weekly Data (2021-2025)") for t in TICKERS_ORIGINAL}
WEEKLY_DIRS.update({t: Path("GST Data/Weekly Data (2021-2025 Broad50 Clear)") for t in TICKERS_BROAD50_CLEAR})

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
OUT_PATH = Path("Live Signal Engine") / "Task1_SpikeAcceleration_Results.csv"

ROLLING_WINDOW = 12
MIN_PERIODS = 8
Z_THRESHOLD = 5.0
N_PERMUTATIONS = 10000
RANDOM_SEED = 42


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


def compute_full_zscore_series(df: pd.DataFrame) -> pd.DataFrame:
    rolling = df["gst"].shift(1).rolling(window=ROLLING_WINDOW, min_periods=MIN_PERIODS)
    df = df.copy()
    df["zscore"] = (df["gst"] - rolling.mean()) / rolling.std()
    df["zscore"] = df["zscore"].replace([np.inf, -np.inf], np.nan)
    return df


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
    print("*** TASK 1: Spike acceleration (delta_z) ***\n")

    events = pd.read_csv(GROUP_A_PATH)
    events = events[events["zscore"] >= Z_THRESHOLD].copy()
    events["spike_week"] = pd.to_datetime(events["spike_week"])
    print(f"z>={Z_THRESHOLD:g} STRONG_EARNINGS events: n={len(events)}\n")

    print("Recomputing full weekly z-score series per ticker...")
    zscore_cache: dict[str, pd.DataFrame] = {}
    for ticker in events["ticker"].unique():
        weekly = load_full_weekly_series(ticker)
        if weekly.empty:
            continue
        zscore_cache[ticker] = compute_full_zscore_series(weekly)
    print(f"Built z-score series for {len(zscore_cache)} tickers.\n")

    rows = []
    n_missing = 0
    for _, ev in events.iterrows():
        ticker, anchor = ev["ticker"], ev["spike_week"]
        z_series = zscore_cache.get(ticker)
        if z_series is None:
            n_missing += 1
            continue

        current_row = z_series[z_series["Week"] == anchor]
        prior_row = z_series[z_series["Week"] == (anchor - timedelta(days=7))]
        if current_row.empty or prior_row.empty or current_row["zscore"].isna().any() or prior_row["zscore"].isna().any():
            n_missing += 1
            continue

        current_z = float(current_row["zscore"].iloc[0])
        prior_z = float(prior_row["zscore"].iloc[0])
        delta_z = current_z - prior_z
        direction = "accelerating" if delta_z > 0 else "decelerating"

        rows.append({
            "ticker": ticker, "spike_week": anchor.date(), "zscore": ev["zscore"],
            "prior_week_zscore": round(prior_z, 3), "delta_z": round(delta_z, 3), "direction": direction,
            "end_of_spike_week_win": ev["end_of_spike_week_win"],
            "end_of_spike_week_pnl_pct": ev["end_of_spike_week_pnl_pct"],
        })

    if n_missing:
        print(f"NOTE: {n_missing} event(s) excluded — missing prior-week z-score (e.g. spike falls too early "
              f"in a ticker's history for a full rolling baseline).\n")

    result = pd.DataFrame(rows)
    result.to_csv(OUT_PATH, index=False)

    win_col, pnl_col = "end_of_spike_week_win", "end_of_spike_week_pnl_pct"
    accel = result[result["direction"] == "accelerating"]
    decel = result[result["direction"] == "decelerating"]
    accel_u = accel[accel[win_col].notna()]
    decel_u = decel[decel[win_col].notna()]

    print(f"=== ACCELERATING (delta_z > 0), n={len(accel_u)} ===")
    print(f"win={accel_u[win_col].mean()*100:.1f}%  avg={accel_u[pnl_col].mean():+.1f}%  median={accel_u[pnl_col].median():+.1f}%")
    print(f"=== DECELERATING (delta_z <= 0), n={len(decel_u)} ===")
    print(f"win={decel_u[win_col].mean()*100:.1f}%  avg={decel_u[pnl_col].mean():+.1f}%  median={decel_u[pnl_col].median():+.1f}%")

    if len(accel_u) and len(decel_u):
        rng = np.random.default_rng(RANDOM_SEED)
        diff, p, a_mean, d_mean = two_sample_permutation_test(
            accel_u[pnl_col].to_numpy(dtype=float), decel_u[pnl_col].to_numpy(dtype=float), N_PERMUTATIONS, rng)
        sig = "significant" if p < 0.05 else "not significant"
        print(f"\nDiff (Accelerating - Decelerating): {diff:+.1f} pts   two-sided p={p:.4f} ({sig})")

    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
