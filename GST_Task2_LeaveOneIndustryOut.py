#!/usr/bin/env python3
# TASK 2 — Leave-one-industry-out validation. All on-disk data, no new
# pulls. No parameter is actually FIT here — z>=5 and the pricing model
# are pre-specified constants, not tuned per sector (same situation as
# the earlier walk-forward and ticker-cross-validation tasks). "Hold out"
# means: report that sector's events in isolation AND test them directly
# against the pooled rest of the universe, to see whether that one
# industry is statistically different from everyone else.
#
# Output: Live Signal Engine/LeaveOneIndustryOut_Results.csv

from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
SECTOR_PATH = Path("Live Signal Engine") / "AllTickers_Sectors.csv"
OUT_PATH = Path("Live Signal Engine") / "LeaveOneIndustryOut_Results.csv"

Z_THRESHOLD = 5.0
MIN_N_POWERED = 10
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
    print(f"*** TASK 2: Leave-one-industry-out validation (z>={Z_THRESHOLD:g}) ***\n")

    events = pd.read_csv(GROUP_A_PATH)
    events = events[events["zscore"] >= Z_THRESHOLD].copy()
    sector_df = pd.read_csv(SECTOR_PATH)
    ticker_to_sector = dict(zip(sector_df["ticker"], sector_df["sector"]))
    events["sector"] = events["ticker"].map(ticker_to_sector)

    win_col, pnl_col = "end_of_spike_week_win", "end_of_spike_week_pnl_pct"
    sector_counts = events["sector"].value_counts()
    print(f"Sector event counts:\n{sector_counts.to_string()}\n")

    powered_sectors = sector_counts[sector_counts >= MIN_N_POWERED].index.tolist()
    underpowered_sectors = sector_counts[sector_counts < MIN_N_POWERED].index.tolist()
    print(f"Powered sectors (n>={MIN_N_POWERED}): {powered_sectors}")
    print(f"Underpowered / untestable (n<{MIN_N_POWERED}): {underpowered_sectors}\n")

    rng = np.random.default_rng(RANDOM_SEED)
    rows = []
    for sector in powered_sectors:
        held_out = events[events["sector"] == sector]
        rest = events[events["sector"] != sector]
        ho_u = held_out[held_out[win_col].notna()]
        rest_u = rest[rest[win_col].notna()]

        wr = ho_u[win_col].mean() * 100
        avg = ho_u[pnl_col].mean()
        med = ho_u[pnl_col].median()
        rest_wr = rest_u[win_col].mean() * 100
        rest_med = rest_u[pnl_col].median()

        diff, p = two_sample_permutation_test(ho_u[pnl_col].to_numpy(dtype=float),
                                               rest_u[pnl_col].to_numpy(dtype=float), N_PERMUTATIONS, rng)
        sig = "significant" if p < 0.05 else "not significant"

        print(f"--- Held-out: {sector} (n={len(ho_u)}) ---")
        print(f"  {sector}: win={wr:.1f}%  avg={avg:+.1f}%  median={med:+.1f}%")
        print(f"  Rest of universe (n={len(rest_u)}): win={rest_wr:.1f}%  median={rest_med:+.1f}%")
        print(f"  Diff ({sector} - Rest): {diff:+.1f}pt  p={p:.4f} ({sig})\n")

        rows.append({
            "sector": sector, "n": len(ho_u), "win_rate_pct": round(wr, 1),
            "avg_pnl_pct": round(avg, 1), "median_pnl_pct": round(med, 1),
            "rest_n": len(rest_u), "rest_win_rate_pct": round(rest_wr, 1), "rest_median_pnl_pct": round(rest_med, 1),
            "diff_vs_rest_pnl_pct": round(diff, 1), "p_value": round(p, 4), "significant": p < 0.05,
            "status": "powered",
        })

    for sector in underpowered_sectors:
        sub = events[events["sector"] == sector]
        sub_u = sub[sub[win_col].notna()]
        n = len(sub_u)
        wr = sub_u[win_col].mean() * 100 if n else None
        med = sub_u[pnl_col].median() if n else None
        rows.append({
            "sector": sector, "n": n, "win_rate_pct": round(wr, 1) if wr is not None else None,
            "avg_pnl_pct": None, "median_pnl_pct": round(med, 1) if med is not None else None,
            "rest_n": None, "rest_win_rate_pct": None, "rest_median_pnl_pct": None,
            "diff_vs_rest_pnl_pct": None, "p_value": None, "significant": None,
            "status": "underpowered_untestable",
        })
        print(f"--- {sector} (n={n}): UNDERPOWERED, flagged untestable, reported descriptively only ---")

    result = pd.DataFrame(rows)
    result.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
