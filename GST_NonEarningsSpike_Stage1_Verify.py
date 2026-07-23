#!/usr/bin/env python3
# NON-EARNINGS SPIKE TEST -- STAGE 1: re-verify candidates with the
# CANONICAL fixed-window method.
#
# Candidates are first identified cheaply from the existing full weekly
# z-score series (AllTickers_ZscoreSeries.csv, "zscore_simple" -- the
# ORIGINAL per-calendar-year chunked method, known to have a cross-year
# discontinuity risk), filtered to z>=5 AND NOT within
# EARNINGS_WINDOW_DAYS=5 calendar days of an earnings date, then
# 21-day-min-gap deduped (same convention as every prior spike-detection
# pass in this project). This gives 72 candidates across 32 tickers.
#
# Since the chunked method is KNOWN to be unreliable (that's the entire
# reason the fixed-window method became canonical), every candidate is
# re-verified here with an independent ~300-day pytrends pull ending at
# spike_week+7 (never extending past it, never stitched across years) --
# the exact same methodology as GST_FixedWindow_PerEvent_Canonical.py,
# reused, not re-derived. Only candidates that STILL clear z>=5 under the
# canonical method proceed to stage 2 (EDGAR contamination check).
#
# Output: Live Signal Engine/NonEarningsSpike_Stage1_Verified.csv

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import sys
import time
import random
import pandas as pd
from pytrends.request import TrendReq

import GST_FixedWindow_PerEvent_Canonical as base

sys.stdout.reconfigure(encoding="utf-8")

ZSCORE_SERIES_PATH = Path("Live Signal Engine") / "AllTickers_ZscoreSeries.csv"
EARNINGS_PATH = Path("Live Signal Engine") / "AllTickers_EarningsDates.csv"
OUT_PATH = Path("Live Signal Engine") / "NonEarningsSpike_Stage1_Verified.csv"

Z_THRESHOLD = 5.0
EARNINGS_WINDOW_DAYS = 5
MIN_GAP_DAYS = 21


def main():
    print("*** NON-EARNINGS SPIKE TEST -- STAGE 1: candidate identification + fixed-window verification ***\n")

    zs = pd.read_csv(ZSCORE_SERIES_PATH)
    zs["week"] = pd.to_datetime(zs["week"])
    earn = pd.read_csv(EARNINGS_PATH)
    earn["earnings_date"] = pd.to_datetime(earn["earnings_date"])
    earnings_by_ticker = {t: sorted(g["earnings_date"].tolist()) for t, g in earn.groupby("ticker")}

    def near_earnings(ticker, week):
        dates = earnings_by_ticker.get(ticker, [])
        return any(abs((week - ed).days) <= EARNINGS_WINDOW_DAYS for ed in dates)

    raw_candidates = zs[zs["zscore_simple"] >= Z_THRESHOLD].copy()
    raw_candidates["near_earnings"] = [near_earnings(r.ticker, r.week) for r in raw_candidates.itertuples()]
    non_earnings = raw_candidates[~raw_candidates["near_earnings"]].copy()

    deduped_rows = []
    for ticker, grp in non_earnings.groupby("ticker"):
        grp = grp.sort_values("week")
        last_date = None
        for _, r in grp.iterrows():
            if last_date is None or (r["week"] - last_date).days >= MIN_GAP_DAYS:
                deduped_rows.append(r)
                last_date = r["week"]
    candidates = pd.DataFrame(deduped_rows).reset_index(drop=True)
    print(f"Candidates (chunked-method z>=5, non-earnings, 21-day deduped): n={len(candidates)} "
          f"across {candidates['ticker'].nunique()} tickers\n")

    pt = TrendReq(hl="en-US", tz=0, timeout=(30, 60), retries=0, backoff_factor=0.0, requests_args={"verify": False})

    rows = []
    for i, r in enumerate(candidates.itertuples(index=False), start=1):
        ticker, anchor, old_z = r.ticker, r.week, r.zscore_simple
        weekly = base.fetch_event_window(pt, ticker, anchor)
        aligned_week, new_z, note = base.compute_zscore_at_anchor(weekly, anchor)

        still_qualifies = (new_z is not None) and (new_z >= Z_THRESHOLD)
        rows.append({
            "ticker": ticker, "spike_week": anchor.date(), "old_zscore_chunked": round(float(old_z), 3),
            "fixed_window_zscore": round(new_z, 4) if new_z is not None else None,
            "still_qualifies_z5": still_qualifies, "note": note,
        })
        print(f"[{i}/{len(candidates)}] {ticker} {anchor.date()}: chunked_z={old_z:.2f} -> "
              f"fixed_window_z={'None' if new_z is None else round(new_z,3)} "
              f"{'QUALIFIES' if still_qualifies else 'DROPPED'} {note}")

        time.sleep(random.uniform(1.2, 2.2))

    result_df = pd.DataFrame(rows)
    result_df.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}\n")

    verified = result_df[result_df["still_qualifies_z5"] == True]  # noqa: E712
    print(f"=== RESULTS ===")
    print(f"Candidates (chunked method): {len(candidates)}")
    print(f"Still qualify z>=5 under fixed-window method: {len(verified)}")
    print(f"Dropped (chunked-method artifact): {len(candidates) - len(verified)}")
    print(f"\nVerified non-earnings spikes proceeding to stage 2 (EDGAR contamination check):")
    print(verified[["ticker", "spike_week", "fixed_window_zscore"]].to_string(index=False))


if __name__ == "__main__":
    main()
