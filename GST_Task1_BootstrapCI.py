#!/usr/bin/env python3
# TASK 1 — Bootstrap confidence intervals for win rate and median P&L,
# z>=5 and z>=6 STRONG_EARNINGS subsets, both horizons. All on-disk data,
# no new pulls: reuses Earnings-Adjacent Spike vs No-Spike Test/
# group_a_z4_earnings_adjacent.csv (already-computed earnings-aware P&L).
#
# Method: resample each subset WITH REPLACEMENT (n = original sample size)
# 10,000 times; each resample's win rate and median P&L are one draw from
# the bootstrap distribution. 95% CI = 2.5th/97.5th percentile of that
# distribution (percentile method). SE = std dev of the distribution.
#
# Output: Live Signal Engine/Task1_BootstrapCI_Results.csv

from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
OUT_PATH = Path("Live Signal Engine") / "Task1_BootstrapCI_Results.csv"

N_BOOTSTRAP = 10000
RANDOM_SEED = 42
HORIZONS = ["end_of_spike_week", "end_of_window"]
THRESHOLDS = [5, 6]


def bootstrap_stats(win: np.ndarray, pnl: np.ndarray, n_boot: int, rng: np.random.Generator) -> dict:
    n = len(win)
    boot_win_rates = np.empty(n_boot)
    boot_medians = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boot_win_rates[i] = win[idx].mean()
        boot_medians[i] = np.median(pnl[idx])

    return {
        "observed_win_rate_pct": round(win.mean() * 100, 2),
        "win_rate_ci_low_pct": round(np.percentile(boot_win_rates, 2.5) * 100, 2),
        "win_rate_ci_high_pct": round(np.percentile(boot_win_rates, 97.5) * 100, 2),
        "win_rate_se_pct": round(boot_win_rates.std() * 100, 2),
        "observed_median_pnl_pct": round(float(np.median(pnl)), 2),
        "median_pnl_ci_low_pct": round(float(np.percentile(boot_medians, 2.5)), 2),
        "median_pnl_ci_high_pct": round(float(np.percentile(boot_medians, 97.5)), 2),
        "median_pnl_se_pct": round(float(boot_medians.std()), 2),
    }


def main():
    print(f"*** TASK 1: Bootstrap CIs (n_bootstrap={N_BOOTSTRAP}, seed={RANDOM_SEED}) ***\n")

    df = pd.read_csv(GROUP_A_PATH)
    rng = np.random.default_rng(RANDOM_SEED)

    rows = []
    for threshold in THRESHOLDS:
        sub = df[df["zscore"] >= threshold]
        for h in HORIZONS:
            win_col, pnl_col = f"{h}_win", f"{h}_pnl_pct"
            usable = sub[sub[win_col].notna()]
            win = usable[win_col].to_numpy(dtype=bool)
            pnl = usable[pnl_col].to_numpy(dtype=float)

            stats = bootstrap_stats(win, pnl, N_BOOTSTRAP, rng)
            row = {"threshold": f"z>={threshold}", "horizon": h, "n": len(usable), **stats}
            rows.append(row)

            print(f"z>={threshold}, {h} (n={len(usable)}):")
            print(f"  win rate: {stats['observed_win_rate_pct']:.1f}%  "
                  f"95% CI [{stats['win_rate_ci_low_pct']:.1f}%, {stats['win_rate_ci_high_pct']:.1f}%]  "
                  f"SE={stats['win_rate_se_pct']:.2f}%")
            print(f"  median P&L: {stats['observed_median_pnl_pct']:+.1f}%  "
                  f"95% CI [{stats['median_pnl_ci_low_pct']:+.1f}%, {stats['median_pnl_ci_high_pct']:+.1f}%]  "
                  f"SE={stats['median_pnl_se_pct']:.2f}pts")
            print()

    result = pd.DataFrame(rows)
    result.to_csv(OUT_PATH, index=False)
    print(f"Wrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
