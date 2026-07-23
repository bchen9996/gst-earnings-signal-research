#!/usr/bin/env python3
# TASK 3 — Earnings calendar density. All on-disk data, no new pulls:
# reuses AllTickers_EarningsDates.csv, AllTickers_Sectors.csv, and
# group_a_z4_earnings_adjacent.csv.
#
# For each z>=5 event, counts how many OTHER tickers (of the 51) have an
# earnings date within 3 days of the same anchor. dense week = 3+ other
# reporters nearby; sparse week = 0-2.
#
# Output: Live Signal Engine/EarningsCalendarDensity_Results.csv

from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
EARNINGS_PATH = Path("Live Signal Engine") / "AllTickers_EarningsDates.csv"
SECTOR_PATH = Path("Live Signal Engine") / "AllTickers_Sectors.csv"
OUT_PATH = Path("Live Signal Engine") / "EarningsCalendarDensity_Results.csv"

Z_THRESHOLD = 5.0
DENSITY_WINDOW_DAYS = 3
DENSE_THRESHOLD = 3
N_PERMUTATIONS = 10000
RANDOM_SEED = 42


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
    print(f"*** TASK 3: Earnings calendar density (z>={Z_THRESHOLD:g}, +/-{DENSITY_WINDOW_DAYS}d) ***\n")

    events = pd.read_csv(GROUP_A_PATH)
    events = events[events["zscore"] >= Z_THRESHOLD].copy()
    events["spike_week"] = pd.to_datetime(events["spike_week"])
    print(f"Total z>={Z_THRESHOLD:g} STRONG_EARNINGS events: n={len(events)}\n")

    earnings_df = pd.read_csv(EARNINGS_PATH)
    earnings_df["earnings_date"] = pd.to_datetime(earnings_df["earnings_date"])
    earnings_by_ticker = {t: g["earnings_date"].tolist() for t, g in earnings_df.groupby("ticker")}

    sector_df = pd.read_csv(SECTOR_PATH)
    ticker_to_sector = dict(zip(sector_df["ticker"], sector_df["sector"]))

    rows = []
    for _, ev in events.iterrows():
        ticker, anchor, zscore = ev["ticker"], ev["spike_week"], ev["zscore"]
        others_reporting = []
        for other, dates in earnings_by_ticker.items():
            if other == ticker:
                continue
            if any(abs((d - anchor).days) <= DENSITY_WINDOW_DAYS for d in dates):
                others_reporting.append(other)
        density = len(others_reporting)
        classification = "dense" if density >= DENSE_THRESHOLD else "sparse"
        rows.append({
            "ticker": ticker, "spike_week": anchor.date(), "zscore": zscore, "sector": ticker_to_sector.get(ticker),
            "n_other_reporters_nearby": density, "other_reporters": ", ".join(sorted(others_reporting)),
            "classification": classification,
            "end_of_spike_week_win": ev["end_of_spike_week_win"],
            "end_of_spike_week_pnl_pct": ev["end_of_spike_week_pnl_pct"],
        })

    result = pd.DataFrame(rows)
    win_col, pnl_col = "end_of_spike_week_win", "end_of_spike_week_pnl_pct"

    dense = result[result["classification"] == "dense"]
    sparse = result[result["classification"] == "sparse"]
    dense_u = dense[dense[win_col].notna()]
    sparse_u = sparse[sparse[win_col].notna()]

    print(f"=== RESULTS (spike_week horizon) ===")
    print(f"Dense week (>={DENSE_THRESHOLD} other reporters nearby): n={len(dense_u):<4} win={dense_u[win_col].mean()*100:5.1f}%  "
          f"avg={dense_u[pnl_col].mean():+7.1f}%  median={dense_u[pnl_col].median():+7.1f}%")
    print(f"Sparse week (0-{DENSE_THRESHOLD-1} other reporters):        n={len(sparse_u):<4} win={sparse_u[win_col].mean()*100:5.1f}%  "
          f"avg={sparse_u[pnl_col].mean():+7.1f}%  median={sparse_u[pnl_col].median():+7.1f}%")

    rng = np.random.default_rng(RANDOM_SEED)
    diff, p = two_sample_permutation_test(dense_u[pnl_col].to_numpy(dtype=float),
                                           sparse_u[pnl_col].to_numpy(dtype=float), N_PERMUTATIONS, rng)
    sig = "significant" if p < 0.05 else "not significant"
    print(f"\nDiff (Dense - Sparse), P&L: {diff:+.1f}pt  p={p:.4f} ({sig})")

    print(f"\n=== SECTOR COMPOSITION — dense vs sparse (flag if dense == big-tech-earnings-week) ===")
    print("Dense week sector counts:")
    print(dense["sector"].value_counts().to_string())
    print("\nSparse week sector counts:")
    print(sparse["sector"].value_counts().to_string())

    result.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
