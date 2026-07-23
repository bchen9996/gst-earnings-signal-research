#!/usr/bin/env python3
# TASK 2 — First spike vs repeated spike. All on-disk data, no new pulls:
# self-referential lookback within the existing 147-event z>=5
# STRONG_EARNINGS list (Earnings-Adjacent Spike vs No-Spike Test/
# group_a_z4_earnings_adjacent.csv).
#
# *** CLASSIFICATION CAVEAT — DISCLOSED ***
# "First spike" means no OTHER z>=5 STRONG_EARNINGS event exists for the
# same ticker in the 39 weeks (~3 earnings quarters) immediately prior,
# WITHIN THIS PROJECT'S KNOWN 2021-2025 EVENT LIST. For events early in
# the window (2021), there may be insufficient lookback history within the
# dataset to know whether a real prior occurrence existed before the data
# starts — those events could be mislabeled "first spike" when a true
# first occurrence is simply outside the observable window. This is a
# real, disclosed limitation, not a data quality issue to hide.
#
# Output: Live Signal Engine/Task2_FirstVsRepeatedSpike_Results.csv

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import sys
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
OUT_PATH = Path("Live Signal Engine") / "Task2_FirstVsRepeatedSpike_Results.csv"

Z_THRESHOLD = 5.0
LOOKBACK_WEEKS = 39
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
    print(f"*** TASK 2: First spike vs repeated spike (z>={Z_THRESHOLD:g}, {LOOKBACK_WEEKS}wk lookback) ***\n")

    events = pd.read_csv(GROUP_A_PATH)
    events = events[events["zscore"] >= Z_THRESHOLD].copy()
    events["spike_week"] = pd.to_datetime(events["spike_week"])
    print(f"Total z>={Z_THRESHOLD:g} STRONG_EARNINGS events: n={len(events)}\n")

    by_ticker = {t: sorted(g["spike_week"].tolist()) for t, g in events.groupby("ticker")}

    classifications = []
    for _, ev in events.iterrows():
        ticker, anchor = ev["ticker"], ev["spike_week"]
        prior_window_start = anchor - timedelta(weeks=LOOKBACK_WEEKS)
        others = [w for w in by_ticker[ticker] if prior_window_start <= w < anchor]
        classifications.append("repeated_spike" if others else "first_spike")
    events["classification"] = classifications

    win_col, pnl_col = "end_of_spike_week_win", "end_of_spike_week_pnl_pct"
    first_events = events[events["classification"] == "first_spike"]
    repeated_events = events[events["classification"] == "repeated_spike"]
    first_u = first_events[first_events[win_col].notna()]
    repeated_u = repeated_events[repeated_events[win_col].notna()]

    print(f"=== RESULTS (spike_week horizon) ===")
    print(f"First spike:     n={len(first_u):<4} win={first_u[win_col].mean()*100:5.1f}%  "
          f"avg={first_u[pnl_col].mean():+7.1f}%  median={first_u[pnl_col].median():+7.1f}%")
    print(f"Repeated spike:  n={len(repeated_u):<4} win={repeated_u[win_col].mean()*100:5.1f}%  "
          f"avg={repeated_u[pnl_col].mean():+7.1f}%  median={repeated_u[pnl_col].median():+7.1f}%")

    rng = np.random.default_rng(RANDOM_SEED)
    diff, p = two_sample_permutation_test(first_u[pnl_col].to_numpy(dtype=float),
                                           repeated_u[pnl_col].to_numpy(dtype=float), N_PERMUTATIONS, rng)
    sig = "significant" if p < 0.05 else "not significant"
    print(f"\nDiff (First - Repeated), P&L: {diff:+.1f}pt  p={p:.4f} ({sig})")

    print(f"\n=== TICKER COMPOSITION — flag if a few high-frequency tickers dominate 'repeated' ===")
    repeated_counts = repeated_events["ticker"].value_counts()
    print("Repeated-spike group ticker counts:")
    print(repeated_counts.to_string())
    top5_share = repeated_counts.head(5).sum() / len(repeated_events) * 100
    print(f"\nTop 5 tickers account for {top5_share:.1f}% of the repeated-spike group (n={len(repeated_events)}).")

    print("\nFirst-spike group ticker counts:")
    print(first_events["ticker"].value_counts().to_string())

    events.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
