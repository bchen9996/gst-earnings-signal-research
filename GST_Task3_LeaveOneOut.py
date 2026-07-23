#!/usr/bin/env python3
# TASK 3 — Leave-one-out outlier analysis. All on-disk data, no new pulls:
# reuses Earnings-Adjacent Spike vs No-Spike Test/
# group_a_z4_earnings_adjacent.csv (z>=5 subset, n=147).
#
# Output: Live Signal Engine/LeaveOneOut_Results.csv

from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
OUT_PATH = Path("Live Signal Engine") / "LeaveOneOut_Results.csv"

Z_THRESHOLD = 5.0
WIN_RATE_INFLUENCE_THRESHOLD_PP = 2.0
MEDIAN_PNL_INFLUENCE_THRESHOLD_PT = 20.0
TRIM_PCT = 0.05


def main():
    print(f"*** TASK 3: Leave-one-out outlier analysis (z>={Z_THRESHOLD:g}) ***\n")

    events = pd.read_csv(GROUP_A_PATH)
    events = events[events["zscore"] >= Z_THRESHOLD].copy()
    win_col, pnl_col = "end_of_spike_week_win", "end_of_spike_week_pnl_pct"
    events = events[events[win_col].notna()].reset_index(drop=True)
    n = len(events)
    print(f"Total z>={Z_THRESHOLD:g} STRONG_EARNINGS events with usable P&L: n={n}\n")

    full_win_rate = events[win_col].mean() * 100
    full_median_pnl = events[pnl_col].median()
    print(f"Full-sample baseline: win={full_win_rate:.2f}%  median={full_median_pnl:+.2f}%\n")

    loo_win_rates, loo_medians = [], []
    high_influence_rows = []
    for i in range(n):
        remaining = events.drop(index=i)
        loo_wr = remaining[win_col].mean() * 100
        loo_med = remaining[pnl_col].median()
        loo_win_rates.append(loo_wr)
        loo_medians.append(loo_med)

        wr_shift = loo_wr - full_win_rate
        med_shift = loo_med - full_median_pnl
        if abs(wr_shift) > WIN_RATE_INFLUENCE_THRESHOLD_PP or abs(med_shift) > MEDIAN_PNL_INFLUENCE_THRESHOLD_PT:
            row = events.iloc[i]
            high_influence_rows.append({
                "ticker": row["ticker"], "spike_week": row["spike_week"], "zscore": row["zscore"],
                "own_win": row[win_col], "own_pnl_pct": row[pnl_col],
                "win_rate_shift_pp": round(wr_shift, 2), "median_pnl_shift_pt": round(med_shift, 2),
            })

    loo_win_arr = np.array(loo_win_rates)
    loo_med_arr = np.array(loo_medians)

    print("=== LEAVE-ONE-OUT WIN RATE DISTRIBUTION (146-event recomputations, n=147 draws) ===")
    print(f"min={loo_win_arr.min():.2f}%  max={loo_win_arr.max():.2f}%  mean={loo_win_arr.mean():.2f}%  "
          f"std={loo_win_arr.std():.3f}pp  range={loo_win_arr.max()-loo_win_arr.min():.2f}pp\n")

    print("=== LEAVE-ONE-OUT MEDIAN P&L DISTRIBUTION ===")
    print(f"min={loo_med_arr.min():+.2f}%  max={loo_med_arr.max():+.2f}%  mean={loo_med_arr.mean():+.2f}%  "
          f"std={loo_med_arr.std():.3f}pt  range={loo_med_arr.max()-loo_med_arr.min():.2f}pt\n")

    print(f"=== HIGH-INFLUENCE EVENTS (removal shifts win rate >{WIN_RATE_INFLUENCE_THRESHOLD_PP}pp "
          f"OR median P&L >{MEDIAN_PNL_INFLUENCE_THRESHOLD_PT}pt) ===")
    if high_influence_rows:
        hi_df = pd.DataFrame(high_influence_rows).sort_values("median_pnl_shift_pt", key=abs, ascending=False)
        print(hi_df.to_string(index=False))
    else:
        print("None found — no single event's removal materially shifts win rate or median P&L. "
              "The result is NOT driven by one or two outlier events.")

    sorted_pnl = events[pnl_col].sort_values().to_numpy()
    trim_n = int(round(len(sorted_pnl) * TRIM_PCT))
    trimmed = sorted_pnl[trim_n: len(sorted_pnl) - trim_n] if trim_n > 0 else sorted_pnl
    trimmed_mean = float(trimmed.mean())
    print(f"\n=== TRIMMED MEAN P&L (drop top/bottom {TRIM_PCT*100:.0f}%, {trim_n} events each end, "
          f"n={len(trimmed)} remaining) ===")
    print(f"Trimmed mean P&L: {trimmed_mean:+.2f}%   (untrimmed mean: {events[pnl_col].mean():+.2f}%, "
          f"untrimmed median: {full_median_pnl:+.2f}%)")

    per_event = events[["ticker", "spike_week", "zscore", win_col, pnl_col]].copy()
    per_event["loo_win_rate_pct"] = loo_win_arr
    per_event["loo_median_pnl_pct"] = loo_med_arr
    per_event["win_rate_shift_pp"] = loo_win_arr - full_win_rate
    per_event["median_pnl_shift_pt"] = loo_med_arr - full_median_pnl
    per_event["high_influence"] = (per_event["win_rate_shift_pp"].abs() > WIN_RATE_INFLUENCE_THRESHOLD_PP) | \
                                   (per_event["median_pnl_shift_pt"].abs() > MEDIAN_PNL_INFLUENCE_THRESHOLD_PT)
    per_event.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
