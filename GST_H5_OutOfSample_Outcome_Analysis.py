#!/usr/bin/env python3
# HYPOTHESIS #5 -- OUT-OF-SAMPLE OUTCOME-SIDE DATA ASSEMBLY.
#
# NAMING NOTE, flagged explicitly: the task that requested this asked for
# "QC_H5_OutOfSample_Outcome_Pull.py." Named GST_ instead, matching this
# project's own convention (QC_ prefix = paste into QuantConnect Research
# and run there; GST_ prefix = runs locally). This script needs NO new
# QuantConnect/AlgoSeek data -- confirmed directly against
# GST_VolatilitySurprise_Analysis.py before writing this:
#   implied_move_pct := real_cost_pct_of_spot -- already pulled, already
#     sitting in Live Signal Engine/QC_H5_OutOfSample_RawResults.csv and
#     QC_H5_OutOfSample_Supplemental_RawResults.csv. No further quote pull
#     needed for this side at all.
#   realized_move_pct := |cumulative stock return, entry_date -> exit_date|
#     x 100 -- computed from LOCAL daily excess-return data
#     (base.load_daily_excess / base.nearest_trading_day_on_or_before /
#     base.cumulative_return, imported directly from
#     GST_FixedWindow_PerEvent_Canonical.py, not reimplemented), exactly
#     the same as the original 76-event test. A "QC_*.py" name would
#     misrepresent this as a QuantConnect notebook script when it is not.
#
# volatility_surprise_pct := realized_move_pct - implied_move_pct --
# identical formula to GST_VolatilitySurprise_Analysis.py, not redefined.
#
# Input: the 49 clean-and-priced events (corrupted==False,
# real_cost_pct_of_spot notna) across
# Live Signal Engine/QC_H5_OutOfSample_RawResults.csv (45-event pull) and
# Live Signal Engine/QC_H5_OutOfSample_Supplemental_RawResults.csv
# (31-event pull).
#
# THIS SCRIPT ONLY ASSEMBLES THE PER-EVENT DATASET. It does NOT compute or
# print any correlation, r, or p-value -- that is a separate, explicitly
# gated step per H5_OutOfSample_PreRegistration.md.
#
# Output: Live Signal Engine/H5_OutOfSample_Outcome_Data.csv

from __future__ import annotations
from pathlib import Path
import sys
import pandas as pd

import GST_FixedWindow_PerEvent_Canonical as base

sys.stdout.reconfigure(encoding="utf-8")

RESULTS_PATHS = [
    Path("Live Signal Engine") / "QC_H5_OutOfSample_RawResults.csv",
    Path("Live Signal Engine") / "QC_H5_OutOfSample_Supplemental_RawResults.csv",
]
OUT_PATH = Path("Live Signal Engine") / "H5_OutOfSample_Outcome_Data.csv"

ENTRY_OFFSET_DAYS = 2
EXIT_OFFSET_DAYS = 6


def main():
    print("*** H5 OUT-OF-SAMPLE -- OUTCOME-SIDE DATA ASSEMBLY (no correlation computed here) ***\n")

    frames = []
    for p in RESULTS_PATHS:
        df = pd.read_csv(p)
        df["spike_week"] = pd.to_datetime(df["spike_week"])
        df["source_file"] = p.name
        frames.append(df)
    combined = pd.concat(frames, ignore_index=True)
    print(f"Loaded {len(combined)} total rows across {len(RESULTS_PATHS)} raw-results files")

    clean = combined[(combined["corrupted"] == False) & combined["real_cost_pct_of_spot"].notna()].copy()  # noqa: E712
    print(f"Clean-and-priced events (corrupted==False & real_cost_pct_of_spot notna): n={len(clean)}\n")

    daily_cache = {}
    rows = []
    for r in clean.itertuples(index=False):
        ticker, anchor = r.ticker, r.spike_week
        row = {
            "ticker": ticker, "spike_week": anchor.date(), "zscore": r.zscore,
            "implied_move_pct": r.real_cost_pct_of_spot,
            "entry_date": None, "exit_date": None,
            "realized_move_pct": None, "volatility_surprise_pct": None,
            "source_file": r.source_file, "note": "",
        }

        if ticker not in daily_cache:
            daily_cache[ticker] = base.load_daily_excess(ticker)
        daily = daily_cache[ticker]
        ret_col = f"{ticker} Daily Return"

        if daily.empty or ret_col not in daily.columns:
            row["note"] = "missing local daily excess-return data"
            rows.append(row)
            print(f"[{ticker} {anchor.date()}] {row['note']}")
            continue

        entry_date = base.nearest_trading_day_on_or_before(daily, anchor + pd.Timedelta(days=ENTRY_OFFSET_DAYS))
        exit_date = base.nearest_trading_day_on_or_before(daily, anchor + pd.Timedelta(days=EXIT_OFFSET_DAYS))
        if entry_date is None or exit_date is None or exit_date <= entry_date:
            row["note"] = "could not resolve entry/exit trading days"
            rows.append(row)
            print(f"[{ticker} {anchor.date()}] {row['note']}")
            continue
        row["entry_date"], row["exit_date"] = entry_date.date(), exit_date.date()

        cum_ret = base.cumulative_return(daily, ret_col, entry_date, exit_date)
        if cum_ret is None:
            row["note"] = "no realized-return data over entry-exit window"
            rows.append(row)
            print(f"[{ticker} {anchor.date()}] {row['note']}")
            continue

        realized_move_pct = abs(cum_ret) * 100
        row["realized_move_pct"] = round(realized_move_pct, 3)
        row["volatility_surprise_pct"] = round(realized_move_pct - r.real_cost_pct_of_spot, 3)
        rows.append(row)
        print(f"[{ticker} {anchor.date()}] realized={realized_move_pct:.2f}%  implied={r.real_cost_pct_of_spot:.2f}%  "
              f"surprise={row['volatility_surprise_pct']:+.2f}pp")

    result_df = pd.DataFrame(rows)
    result_df.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")

    usable = result_df[result_df["volatility_surprise_pct"].notna()]
    print(f"\nEvents with a complete volatility_surprise_pct: {len(usable)} / {len(clean)}")
    if len(usable) < len(clean):
        dropped = result_df[result_df["volatility_surprise_pct"].isna()]
        print("Dropped (see note column):")
        print(dropped[["ticker", "spike_week", "note"]].to_string(index=False))
    print("\n*** No correlation, r, or p-value computed in this script. Data assembly only. ***")


if __name__ == "__main__":
    main()
