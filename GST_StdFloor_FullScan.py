#!/usr/bin/env python3
# STD-FLOOR BUG RESCAN — applies the epsilon-floor fix (STD_EPSILON_FLOOR
# = 1.0, added to GST_FullPopulation_ContinuousWindow_Recompute.py and
# GST_Live_Signal_Engine.py on 2026-07-18, see CHANGELOG.md) and re-pulls
# all 28 tickers in the STRONG_EARNINGS population to find EVERY week
# (any ticker, not just GME) where the raw (unfloored) rolling std
# collapsed below the floor -- i.e. every place the bug could have fired,
# not just the 2 already found on GME. Reports the corrected z-score for
# each such instance, and specifically resolves GME's two previously-
# unresolved dates (2025-09-07, 2024-03-24).
#
# Output: printed report only (no new CSV requested for this pass --
# feeds directly into a CHANGELOG.md update).

from __future__ import annotations
from pathlib import Path
import random
import sys
import time
import numpy as np
import pandas as pd
from pytrends.request import TrendReq

sys.stdout.reconfigure(encoding="utf-8")

from GST_FullPopulation_ContinuousWindow_Recompute import (
    fetch_full_series, compute_zscore, dedupe_spikes, near_earnings_flag,
    PULL_START, PULL_END, STD_EPSILON_FLOOR, STRONG_Z,
)

EARNINGS_PATH = Path("Live Signal Engine") / "AllTickers_EarningsDates.csv"
GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"

GME_TARGET_DATES = [pd.Timestamp("2025-09-07"), pd.Timestamp("2024-03-24")]


def main():
    print(f"*** STD-FLOOR BUG RESCAN (epsilon={STD_EPSILON_FLOOR}) ***\n")

    orig_events = pd.read_csv(GROUP_A_PATH)
    orig_strong = orig_events[(orig_events["zscore"] >= STRONG_Z) & (orig_events["near_earnings"] == True)].copy()  # noqa: E712
    tickers = sorted(orig_strong["ticker"].unique())
    print(f"Scanning {len(tickers)} tickers (full weekly history, {PULL_START} to {PULL_END})\n")

    earnings_df = pd.read_csv(EARNINGS_PATH)
    earnings_df["earnings_date"] = pd.to_datetime(earnings_df["earnings_date"])
    earnings_by_ticker = {t: sorted(g["earnings_date"].tolist()) for t, g in earnings_df.groupby("ticker")}

    pt = TrendReq(hl="en-US", tz=0, timeout=(30, 60), retries=0, backoff_factor=0.0, requests_args={"verify": False})

    all_activations = []
    gme_targets_found = {}

    for i, ticker in enumerate(tickers, start=1):
        weekly = fetch_full_series(pt, ticker)
        if weekly.empty:
            print(f"  [{i}/{len(tickers)}] {ticker}: NO DATA, skipping")
            continue
        weekly = compute_zscore(weekly)   # now includes raw_std + std_floor_activated, with the fix applied

        activated = weekly[weekly["std_floor_activated"]]
        if not activated.empty:
            print(f"  [{i}/{len(tickers)}] {ticker}: {len(activated)} week(s) with std-floor activated (raw_std < {STD_EPSILON_FLOOR})")
            earnings_dates = earnings_by_ticker.get(ticker, [])
            for _, row in activated.iterrows():
                near = near_earnings_flag(row["Week"], earnings_dates)
                clears = row["zscore"] >= STRONG_Z if pd.notna(row["zscore"]) else False
                all_activations.append({
                    "ticker": ticker, "week": row["Week"].date(), "raw_std": round(float(row["raw_std"]), 6),
                    "gst_value": row["gst"], "fixed_zscore": round(float(row["zscore"]), 4) if pd.notna(row["zscore"]) else None,
                    "near_earnings": near, "clears_z5": clears,
                })
        else:
            print(f"  [{i}/{len(tickers)}] {ticker}: clean, no std-floor activations")

        if ticker == "GME":
            for target in GME_TARGET_DATES:
                match = weekly[weekly["Week"] == target]
                if not match.empty:
                    r = match.iloc[0]
                    gme_targets_found[target] = {
                        "raw_std": float(r["raw_std"]) if pd.notna(r["raw_std"]) else None,
                        "fixed_zscore": float(r["zscore"]) if pd.notna(r["zscore"]) else None,
                        "gst_value": int(r["gst"]),
                    }

        time.sleep(random.uniform(1.5, 3.0))

    print(f"\n=== FULL SCAN RESULT ===")
    print(f"Total std-floor activations found (all 28 tickers, full history): {len(all_activations)}")
    if all_activations:
        act_df = pd.DataFrame(all_activations)
        print(act_df.to_string(index=False))
        n_would_clear = act_df["clears_z5"].sum()
        n_near_earnings = act_df["near_earnings"].sum()
        print(f"\nOf these, {n_near_earnings} are near_earnings, and {n_would_clear} clear z>=5 under the FIXED formula.")
    else:
        print("(none found beyond GME)")

    print(f"\n=== GME's two previously-unresolved events, under the FIXED formula ===")
    for target in GME_TARGET_DATES:
        info = gme_targets_found.get(target)
        if info is None:
            print(f"  {target.date()}: not found in recomputed series (no data at this week)")
            continue
        clears = info["fixed_zscore"] is not None and info["fixed_zscore"] >= STRONG_Z
        print(f"  {target.date()}: gst={info['gst_value']}  raw_std={info['raw_std']:.6f}  "
              f"fixed_zscore={info['fixed_zscore']:.4f}  clears_z>=5={clears}")


if __name__ == "__main__":
    main()
