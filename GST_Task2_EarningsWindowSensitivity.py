#!/usr/bin/env python3
# TASK 2 — Days-to-earnings window sensitivity for z>=5 events. All on-disk
# data, no new pulls.
#
# Uses Straddle Profitability Test (2021-2025 51Ticker)/results.csv (ALL
# z>=4 spike events, incl. those NOT near earnings, n=297) filtered to
# zscore>=5 (n=201) — a broader population than the n=147 already-near-
# earnings-only Group A file, needed here because testing cutoffs WIDER
# than 5 days requires events that the original 5-day near_earnings filter
# would have excluded. Joined against the raw nearest_earnings_gap_days
# from Earnings Clustering Test (2021-2025)*/spike_event_earnings_flags.csv
# (both ticker sources) to recover the actual gap distance per event.
#
# *** PRICING CAVEAT — DISCLOSED, NOT SMOOTHED OVER ***
# "Earnings-aware pricing already baked into the file" is reused exactly
# as computed, per the task's instruction — this is NOT re-priced per
# cutoff. That pricing was originally assigned using the ORIGINAL 5-day
# definition: near_earnings=True (gap<=5) events got the calibrated near-
# earnings IV markup (1.2398x), everything else got the naive 1.10x markup.
# Consequence: for cutoffs of 7 and 10 days, the MARGINAL newly-included
# events (gap 6-10) are priced at the naive 1.10x markup, not a
# hypothetically-appropriate 7-or-10-day-window markup (no such markup was
# ever calibrated). Cutoffs of 1, 2, and 3 days are unaffected by this —
# they're strict subsets of the original near-earnings-priced n=147/z>=5
# population, so pricing is internally consistent for those three rows.
#
# Output: Live Signal Engine/Task2_EarningsWindowSensitivity_Results.csv

from __future__ import annotations
from pathlib import Path
import sys
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

RESULTS_PATH = Path("Straddle Profitability Test (2021-2025 51Ticker)") / "results.csv"
FLAGS_PATHS = [
    Path("Earnings Clustering Test (2021-2025)") / "spike_event_earnings_flags.csv",
    Path("Earnings Clustering Test (2021-2025 Broad50 Clear)") / "spike_event_earnings_flags.csv",
]
OUT_PATH = Path("Live Signal Engine") / "Task2_EarningsWindowSensitivity_Results.csv"

Z_THRESHOLD = 5.0
CUTOFFS = [1, 2, 3, 5, 7, 10]
HORIZON = "end_of_spike_week"


def main():
    print(f"*** TASK 2: Days-to-earnings window sensitivity (z>={Z_THRESHOLD:g}) ***\n")

    results = pd.read_csv(RESULTS_PATH)
    events = results[results["zscore"] >= Z_THRESHOLD].copy()
    events["spike_week"] = pd.to_datetime(events["spike_week"]).dt.date.astype(str)
    print(f"Total z>={Z_THRESHOLD:g} events (all, regardless of earnings proximity): n={len(events)}")

    flags_frames = [pd.read_csv(p) for p in FLAGS_PATHS if p.exists()]
    flags = pd.concat(flags_frames, ignore_index=True)
    flags["anchor"] = pd.to_datetime(flags["anchor"]).dt.date.astype(str)
    gap_lookup = {(r["ticker"], r["anchor"]): r["nearest_earnings_gap_days"] for _, r in flags.iterrows()}

    events["gap_days"] = [gap_lookup.get((t, sw)) for t, sw in zip(events["ticker"], events["spike_week"])]
    n_missing = events["gap_days"].isna().sum()
    if n_missing:
        print(f"NOTE: {n_missing} event(s) had no earnings-flag match — excluded from all cutoffs.")
    events = events.dropna(subset=["gap_days"])

    win_col, pnl_col = f"{HORIZON}_win", f"{HORIZON}_pnl_pct"

    rows = []
    for cutoff in CUTOFFS:
        sub = events[events["gap_days"] <= cutoff]
        usable = sub[sub[win_col].notna()]
        n = len(usable)
        if n == 0:
            print(f"cutoff <= {cutoff}d: no usable events")
            continue
        wr = usable[win_col].mean() * 100
        med = usable[pnl_col].median()
        avg = usable[pnl_col].mean()
        pricing_note = "consistent (subset of original near-earnings pricing)" if cutoff <= 5 \
            else "marginal events (gap 6+) priced at naive 1.10x markup, not re-derived"
        rows.append({
            "cutoff_days": cutoff, "n": n, "win_rate_pct": round(wr, 1),
            "avg_pnl_pct": round(avg, 1), "median_pnl_pct": round(med, 1),
            "pricing_basis_note": pricing_note,
        })
        print(f"cutoff <= {cutoff}d: n={n:<4} win={wr:5.1f}%  avg={avg:+7.1f}%  median={med:+7.1f}%   [{pricing_note}]")

    result = pd.DataFrame(rows)
    result.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
