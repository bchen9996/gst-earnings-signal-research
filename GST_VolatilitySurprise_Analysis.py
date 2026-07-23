#!/usr/bin/env python3
# VOLATILITY SURPRISE ANALYSIS -- the decisive check for whether a
# long-volatility strategy (pre-earnings IV trade, filtered straddle) has
# real merit, using the 76-event REAL QuantConnect option-quote validation
# sample (not the Black-Scholes model).
#
# For each event:
#   implied_move_pct = real_cost_pct_of_spot (the REAL quoted ATM straddle
#     ask cost, as % of spot -- the market's actual priced-in expected
#     move, not a model estimate. Already computed and exported in
#     QC_Validation_CleanSample_v2_76Events.csv.)
#   realized_move_pct = |cumulative price return from entry_date to
#     exit_date| -- reconstructed from LOCAL daily excess-return data
#     (entry_date/exit_date are not in the exported QC file, only
#     spike_week; re-derived via the same anchor+2/anchor+6 nearest-
#     trading-day rule used throughout this project). This is the true
#     realized stock move, independent of any option-quote noise
#     (remaining time value, fee rounding) -- a cleaner comparison than
#     using the option's own exit bid value as a realized-move proxy.
#   volatility_surprise_pct = realized_move_pct - implied_move_pct
#
# fixed_window_zscore is joined in from FixedWindow_PerEvent_Canonical.csv
# by (ticker, spike_week) to test whether z-score magnitude predicts
# volatility surprise specifically, or just predicts realized move size
# regardless of what was priced in -- these are two different hypotheses,
# tested separately below.
#
# Output: Live Signal Engine/VolatilitySurprise_Analysis.csv

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import sys
import pandas as pd

import GST_FixedWindow_PerEvent_Canonical as base

sys.stdout.reconfigure(encoding="utf-8")

VALIDATION_PATH = Path("Live Signal Engine") / "QC_Validation_CleanSample_v2_76Events.csv"
CANONICAL_PATH = Path("Live Signal Engine") / "FixedWindow_PerEvent_Canonical.csv"
OUT_PATH = Path("Live Signal Engine") / "VolatilitySurprise_Analysis.csv"

ENTRY_OFFSET_DAYS = 2
EXIT_OFFSET_DAYS = 6


def main():
    print("*** VOLATILITY SURPRISE ANALYSIS (76-event real-quote sample) ***\n")

    val = pd.read_csv(VALIDATION_PATH)
    val["spike_week"] = pd.to_datetime(val["spike_week"])
    print(f"Loaded {len(val)} real-quote validation events\n")

    canon = pd.read_csv(CANONICAL_PATH)
    canon["spike_week"] = pd.to_datetime(canon["spike_week"])
    zmap = canon.set_index(["ticker", "spike_week"])["fixed_window_zscore"].to_dict()

    daily_cache = {}
    rows = []
    for r in val.itertuples(index=False):
        ticker, anchor = r.ticker, r.spike_week
        zscore = zmap.get((ticker, anchor))

        if ticker not in daily_cache:
            daily_cache[ticker] = base.load_daily_excess(ticker)
        daily = daily_cache[ticker]
        ret_col = f"{ticker} Daily Return"

        row = {"ticker": ticker, "spike_week": anchor.date(), "fixed_window_zscore": zscore,
               "implied_move_pct": r.real_cost_pct_of_spot, "realized_move_pct": None,
               "volatility_surprise_pct": None, "note": ""}

        if daily.empty or ret_col not in daily.columns or zscore is None:
            row["note"] = "missing daily data or z-score join failed"
            rows.append(row)
            continue

        entry_date = base.nearest_trading_day_on_or_before(daily, anchor + timedelta(days=ENTRY_OFFSET_DAYS))
        exit_date = base.nearest_trading_day_on_or_before(daily, anchor + timedelta(days=EXIT_OFFSET_DAYS))
        if entry_date is None or exit_date is None or exit_date <= entry_date:
            row["note"] = "could not resolve entry/exit trading days"
            rows.append(row)
            continue

        cum_ret = base.cumulative_return(daily, ret_col, entry_date, exit_date)
        if cum_ret is None:
            row["note"] = "no realized-return data over entry-exit window"
            rows.append(row)
            continue

        realized_move_pct = abs(cum_ret) * 100
        volatility_surprise = realized_move_pct - r.real_cost_pct_of_spot

        row.update({
            "entry_date": entry_date.date(), "exit_date": exit_date.date(),
            "realized_move_pct": round(realized_move_pct, 3),
            "volatility_surprise_pct": round(volatility_surprise, 3),
        })
        rows.append(row)

    result_df = pd.DataFrame(rows)
    result_df.to_csv(OUT_PATH, index=False)
    print(f"Wrote: {OUT_PATH}\n")

    usable = result_df[result_df["volatility_surprise_pct"].notna()].copy()
    print(f"Usable events: {len(usable)} / {len(val)}\n")

    pct_positive = (usable["volatility_surprise_pct"] > 0).mean() * 100
    median_surprise = usable["volatility_surprise_pct"].median()

    corr_z_surprise_pearson = usable["fixed_window_zscore"].corr(usable["volatility_surprise_pct"], method="pearson")
    corr_z_surprise_spearman = usable["fixed_window_zscore"].corr(usable["volatility_surprise_pct"], method="spearman")
    corr_z_realized_pearson = usable["fixed_window_zscore"].corr(usable["realized_move_pct"], method="pearson")
    corr_z_realized_spearman = usable["fixed_window_zscore"].corr(usable["realized_move_pct"], method="spearman")

    print("=== RESULTS ===")
    print(f"n = {len(usable)}")
    print(f"Fraction with POSITIVE volatility surprise (realized > implied): {pct_positive:.1f}%")
    print(f"Median volatility surprise: {median_surprise:+.2f} pct points\n")

    print("Does z-score predict volatility SURPRISE specifically, or just realized MOVE SIZE?")
    print(f"  z-score vs. volatility_surprise_pct:  Pearson r={corr_z_surprise_pearson:.3f}   "
          f"Spearman rho={corr_z_surprise_spearman:.3f}")
    print(f"  z-score vs. realized_move_pct:        Pearson r={corr_z_realized_pearson:.3f}   "
          f"Spearman rho={corr_z_realized_spearman:.3f}")

    if abs(corr_z_surprise_spearman) < 0.15:
        print("\n=> z-score shows little/no relationship with volatility SURPRISE specifically.")
    else:
        print(f"\n=> z-score shows a {'positive' if corr_z_surprise_spearman > 0 else 'negative'} "
              f"relationship with volatility surprise.")


if __name__ == "__main__":
    main()
