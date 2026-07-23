#!/usr/bin/env python3
# LOOK-AHEAD BIAS AUDIT — the full-population continuous-window recompute
# (GST_FullPopulation_ContinuousWindow_Recompute.py) pulled each ticker's
# ENTIRE 2021-2025 history in ONE query. Google Trends rescales its 0-100
# output to the peak WITHIN THE QUERIED WINDOW -- for a single query
# spanning 5 years, that peak is the max across the WHOLE 5 years,
# meaning every week's value (including early-2021 weeks) is expressed
# as "% of whatever the eventual 2021-2025 peak turned out to be," even
# if that peak occurs YEARS after the week being scored. This is
# look-ahead contamination in the 0-100 rescaling step -- distinct from
# the per-year-chunking discontinuity bug and the std-floor bug found
# earlier. The live engine, and the smaller per-event recomputes
# (MSFT_ContinuousWindow_Recompute.csv, GST_Reproducibility_Audit.py),
# do NOT have this problem, because each of THEIR pulls ends at (or
# shortly after) the specific date being scored -- the window never
# extends into that event's own future.
#
# This script: re-pulls all 28 tickers (same 2021-01-01 to 2025-12-31
# window as the full-population recompute), finds each ticker's actual
# peak date (gst==100) within that pulled series, and flags every
# considered event (original 147 + the 28 raw newly-qualifying
# candidates = 175 total) where the event's spike_week PRECEDES that
# ticker's peak date -- i.e., every event where the full-population
# recompute's z-score could have used information from after the event.

from __future__ import annotations
from pathlib import Path
import random
import sys
import time
import pandas as pd
from pytrends.request import TrendReq

sys.stdout.reconfigure(encoding="utf-8")

from GST_FullPopulation_ContinuousWindow_Recompute import fetch_full_series, PULL_START, PULL_END

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
OUT_PATH = Path("Live Signal Engine") / "LookAhead_Audit_Results.csv"

RAW_NEWLY_QUALIFYING_28 = [
    ('LDOS','2021-02-21'), ('NCLH','2021-02-21'), ('LDOS','2021-08-01'), ('STZ','2021-10-03'),
    ('GOOGL','2021-10-24'), ('BKR','2022-01-16'), ('NFLX','2022-01-16'), ('INTC','2022-10-23'),
    ('LDOS','2022-10-30'), ('GPN','2022-10-30'), ('NFLX','2023-01-15'), ('SYK','2023-01-29'),
    ('LDOS','2023-10-29'), ('INTC','2024-01-21'), ('SBUX','2024-01-28'), ('LDOS','2024-02-11'),
    ('NKE','2024-03-17'), ('GME','2024-03-24'), ('GPN','2024-08-04'), ('STZ','2025-01-05'),
    ('SYK','2025-01-26'), ('SBUX','2025-01-26'), ('QCOM','2025-02-02'), ('TTWO','2025-02-02'),
    ('BRK-B','2025-02-23'), ('SYK','2025-07-27'), ('LDOS','2025-08-03'), ('NVDA','2025-08-24'),
]


def main():
    print("*** LOOK-AHEAD BIAS AUDIT — full-population continuous-window recompute ***\n")

    events = pd.read_csv(GROUP_A_PATH)
    strong = events[(events["zscore"] >= 5) & (events["near_earnings"] == True)].copy()  # noqa: E712
    strong["spike_week"] = pd.to_datetime(strong["spike_week"])
    tickers = sorted(strong["ticker"].unique())

    all_considered = [(row["ticker"], row["spike_week"]) for _, row in strong.iterrows()]
    all_considered += [(t, pd.Timestamp(d)) for t, d in RAW_NEWLY_QUALIFYING_28]

    pt = TrendReq(hl="en-US", tz=0, timeout=(30, 60), retries=0, backoff_factor=0.0, requests_args={"verify": False})

    print(f"Re-pulling {len(tickers)} tickers (same window as the full-population recompute: {PULL_START} to {PULL_END})...")
    peak_dates = {}
    peak_values = {}
    for i, ticker in enumerate(tickers, start=1):
        weekly = fetch_full_series(pt, ticker)
        if weekly.empty:
            print(f"  [{i}/{len(tickers)}] {ticker}: NO DATA")
            continue
        idx_max = weekly["gst"].idxmax()
        peak_dates[ticker] = weekly.loc[idx_max, "Week"]
        peak_values[ticker] = int(weekly.loc[idx_max, "gst"])
        n_at_100 = int((weekly["gst"] == weekly["gst"].max()).sum())
        print(f"  [{i}/{len(tickers)}] {ticker}: peak={peak_values[ticker]} on {peak_dates[ticker].date()}"
              + (f"  ({n_at_100} weeks tied at peak)" if n_at_100 > 1 else ""))
        time.sleep(random.uniform(1.5, 3.0))

    print(f"\n=== FLAGGING LOOK-AHEAD RISK FOR ALL {len(all_considered)} CONSIDERED EVENTS ===\n")
    rows = []
    for ticker, spike_week in all_considered:
        peak_date = peak_dates.get(ticker)
        if peak_date is None:
            continue
        days_before_peak = (peak_date - spike_week).days
        at_risk = spike_week < peak_date
        rows.append({
            "ticker": ticker, "spike_week": spike_week.date(), "ticker_peak_date": peak_date.date(),
            "days_event_precedes_peak": days_before_peak, "look_ahead_risk": at_risk,
        })

    result = pd.DataFrame(rows).drop_duplicates(subset=["ticker", "spike_week"])
    result.to_csv(OUT_PATH, index=False)
    print(f"Wrote: {OUT_PATH}\n")

    n_at_risk = result["look_ahead_risk"].sum()
    n_total = len(result)
    print(f"Events with look_ahead_risk=True (event date precedes ticker's 2021-2025 peak): {n_at_risk}/{n_total}")
    print(f"\nPer-ticker peak dates:")
    for t in tickers:
        if t in peak_dates:
            print(f"  {t}: peak on {peak_dates[t].date()}")


if __name__ == "__main__":
    main()
