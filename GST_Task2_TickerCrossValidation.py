#!/usr/bin/env python3
# TASK 2 — 5-fold ticker-level cross-validation. All on-disk data, no new
# pulls. Tests whether the STRONG_EARNINGS (z>=5) edge generalizes across
# firms or is concentrated in a handful of tickers.
#
# Splits the 51-ticker universe into 5 groups (~10 each, fixed random
# seed). No parameter is actually FIT from the "train" folds — z>=5 and
# the pricing model are pre-specified constants throughout this project,
# not tuned per fold (same situation as the earlier walk-forward task).
# "Train on 4, test on held-out" here means: report each held-out group's
# results in isolation, so a pooled 76.2%/+130.0% headline can't be hiding
# one or two extreme tickers dragging the average. The aggregate across
# all 5 held-out folds is, by construction, exactly the full 147-event
# population (every ticker appears in exactly one fold's test set) — this
# is reported as a consistency check, not a new number.
#
# Output: Live Signal Engine/Task2_TickerCrossValidation_Results.csv

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

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
OUT_PATH = Path("Live Signal Engine") / "Task2_TickerCrossValidation_Results.csv"

Z_THRESHOLD = 5.0
N_FOLDS = 5
RANDOM_SEED = 42
MIN_N_WARN = 10


def main():
    print(f"*** TASK 2: 5-fold ticker-level cross-validation (z>={Z_THRESHOLD:g}) ***\n")

    rng = np.random.default_rng(RANDOM_SEED)
    shuffled = np.array(ALL_TICKERS)
    rng.shuffle(shuffled)
    folds = np.array_split(shuffled, N_FOLDS)
    for i, f in enumerate(folds, start=1):
        print(f"Fold {i}: {len(f)} tickers — {', '.join(sorted(f))}")
    print()

    events = pd.read_csv(GROUP_A_PATH)
    events = events[events["zscore"] >= Z_THRESHOLD].copy()
    win_col, pnl_col = "end_of_spike_week_win", "end_of_spike_week_pnl_pct"

    rows = []
    for i, fold_tickers in enumerate(folds, start=1):
        sub = events[events["ticker"].isin(fold_tickers)]
        usable = sub[sub[win_col].notna()]
        n = len(usable)
        if n == 0:
            rows.append({"fold": i, "n_tickers": len(fold_tickers), "n_events": 0,
                         "win_rate_pct": None, "median_pnl_pct": None, "avg_pnl_pct": None,
                         "underpowered": True})
            print(f"Fold {i}: n_events=0 (no usable events)")
            continue
        wr = usable[win_col].mean() * 100
        med = usable[pnl_col].median()
        avg = usable[pnl_col].mean()
        underpowered = n < MIN_N_WARN
        rows.append({
            "fold": i, "n_tickers": len(fold_tickers), "n_events": n,
            "win_rate_pct": round(wr, 1), "median_pnl_pct": round(med, 1), "avg_pnl_pct": round(avg, 1),
            "underpowered": underpowered,
        })
        flag = "  [UNDERPOWERED n<10]" if underpowered else ""
        print(f"Fold {i} ({len(fold_tickers)} tickers): n_events={n:<4} win={wr:5.1f}%  "
              f"avg={avg:+7.1f}%  median={med:+7.1f}%{flag}")

    result = pd.DataFrame(rows)
    result.to_csv(OUT_PATH, index=False)

    # Aggregate across all held-out folds -- should equal the full population exactly
    all_usable = events[events[win_col].notna()]
    agg_wr = all_usable[win_col].mean() * 100
    agg_med = all_usable[pnl_col].median()
    agg_avg = all_usable[pnl_col].mean()
    print(f"\n=== AGGREGATE across all 5 held-out folds (== full population, by construction) ===")
    print(f"n={len(all_usable)}  win={agg_wr:.1f}%  avg={agg_avg:+.1f}%  median={agg_med:+.1f}%")
    print(f"(vs established baseline: n=147  win=76.2%  median=+130.0%)")

    fold_win_rates = result["win_rate_pct"].dropna()
    print(f"\nSpread across folds: win rate range [{fold_win_rates.min():.1f}%, {fold_win_rates.max():.1f}%], "
          f"std={fold_win_rates.std():.1f}pt")
    n_underpowered = result["underpowered"].sum()
    if n_underpowered:
        print(f"{n_underpowered}/{N_FOLDS} fold(s) flagged underpowered (n<{MIN_N_WARN}).")

    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
