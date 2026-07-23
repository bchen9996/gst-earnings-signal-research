#!/usr/bin/env python3
# Opening gap by z-score bucket: does gap ALONE cover straddle cost at
# very high z, making open-exit a viable alternative to holding through
# close? Reuses OpeningGap_Analysis.csv (no new pulls) — merges its
# decomp section (log-return move breakdown, pnl_pct) with its spike_gaps
# section (zscore) on (ticker, spike_week).
#
# *** RECOVERING "cost" ***
# The source file didn't persist straddle cost directly. It's recovered
# exactly from what WAS persisted: pnl_pct = (intrinsic - cost)/cost*100
# and intrinsic = |total_move_pct| (both expressed on the same S=100
# basis), so cost = intrinsic / (1 + pnl_pct/100). This is algebra on
# already-computed numbers, not a re-estimate.
#
# *** OPEN-EXIT PNL ***
# log_total = log_gap + log_intraday_exit_day + log_residual (persisted).
# Exiting at the open instead of the close removes the intraday_exit_day
# leg: log_total_open_exit = log_gap + log_residual. Re-priced against the
# SAME recovered cost (cost doesn't depend on the realized move) to get
# pnl_open and win_open.
#
# Output: Live Signal Engine/OpeningGap_ZBucketAnalysis.csv

from __future__ import annotations
from pathlib import Path
import sys
import math
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

SRC_PATH = Path("Live Signal Engine") / "OpeningGap_Analysis.csv"
OUT_PATH = Path("Live Signal Engine") / "OpeningGap_ZBucketAnalysis.csv"

Z_BUCKETS = [(5, 6), (6, 8), (8, 10), (10, 15), (15, np.inf)]


def main():
    print("*** Opening gap by z-score bucket ***\n")

    raw = pd.read_csv(SRC_PATH)
    blank_idx = raw.index[raw.isna().all(axis=1)].tolist()
    decomp = raw.iloc[blank_idx[0] + 1: blank_idx[1]].dropna(axis=1, how="all").copy()
    spike_gaps = raw.iloc[blank_idx[1] + 1: blank_idx[2]].dropna(axis=1, how="all").copy()
    print(f"decomp rows: {len(decomp)}   spike_gaps rows: {len(spike_gaps)}")

    events = decomp.merge(spike_gaps[["ticker", "spike_week", "zscore"]], on=["ticker", "spike_week"], how="left")
    events = events.dropna(subset=["zscore"]).copy()
    for col in ["gap_pct", "total_move_pct", "log_total", "log_gap", "log_intraday_exit_day",
                "log_residual", "pnl_pct", "zscore"]:
        events[col] = events[col].astype(float)
    print(f"Merged events with zscore: n={len(events)}\n")

    # --- recover cost, exactly, from persisted pnl_pct + total_move_pct ---
    intrinsic_close = events["total_move_pct"].abs()
    events["cost"] = intrinsic_close / (1 + events["pnl_pct"] / 100)

    # --- open-exit re-pricing ---
    events["log_total_open_exit"] = events["log_total"] - events["log_intraday_exit_day"]
    events["intrinsic_open"] = (np.exp(events["log_total_open_exit"]) - 1).abs() * 100
    events["pnl_open_pct"] = (events["intrinsic_open"] - events["cost"]) / events["cost"] * 100
    events["win_open"] = events["pnl_open_pct"] > 0
    events["win_close"] = events["pnl_pct"] > 0

    events["gap_covers_cost"] = events["gap_pct"].abs() > events["cost"]

    events["z_bucket"] = pd.cut(events["zscore"], bins=[b[0] for b in Z_BUCKETS] + [np.inf],
                                 labels=[f"{lo}-{hi if hi != np.inf else '+'}" for lo, hi in Z_BUCKETS],
                                 right=False, include_lowest=True)

    print("=== BY Z-SCORE BUCKET ===")
    rows = []
    for label, grp in events.groupby("z_bucket", observed=True):
        n = len(grp)
        if n == 0:
            continue
        mean_abs_gap = grp["gap_pct"].abs().mean()
        frac_gap_covers_cost = grp["gap_covers_cost"].mean() * 100
        win_close = grp["win_close"].mean() * 100
        win_open = grp["win_open"].mean() * 100
        median_pnl_close = grp["pnl_pct"].median()
        median_pnl_open = grp["pnl_open_pct"].median()
        print(f"z={label:<6} n={n:<4} mean|gap|={mean_abs_gap:6.2f}%  gap>cost={frac_gap_covers_cost:5.1f}%  "
              f"win_close={win_close:5.1f}%  win_open={win_open:5.1f}%  "
              f"median_pnl_close={median_pnl_close:+7.1f}%  median_pnl_open={median_pnl_open:+7.1f}%")
        rows.append({"z_bucket": label, "n": n, "mean_abs_gap_pct": round(mean_abs_gap, 2),
                     "pct_gap_covers_cost": round(frac_gap_covers_cost, 1),
                     "win_rate_close_pct": round(win_close, 1), "win_rate_open_pct": round(win_open, 1),
                     "median_pnl_close_pct": round(median_pnl_close, 1), "median_pnl_open_pct": round(median_pnl_open, 1),
                     "win_rate_diff_close_minus_open": round(win_close - win_open, 1)})

    result = pd.DataFrame(rows)
    print(f"\n=== INTERPRETATION ===")
    print("If 'gap>cost' fraction and win_open climb toward win_close at high z, gap alone becomes")
    print("sufficient there (open-exit viable). If win_close stays meaningfully above win_open across")
    print("all buckets, holding through close adds value at every z level, not just moderate z.")

    result.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
