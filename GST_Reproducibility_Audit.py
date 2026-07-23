#!/usr/bin/env python3
# GST REPRODUCIBILITY AUDIT — does re-pulling the EXACT same historical
# Google Trends query produce the same z-score every time? And does the
# search TERM/CATEGORY choice (raw ticker vs company name vs Google's
# Finance category) change the result meaningfully for the same event?
#
# 10 STRONG_EARNINGS events selected across all 5 years (2021-2025) and
# 10 different tickers (fixed seed, stratified by year, distinct tickers
# where possible): MSFT, SBUX, NVDA, INTC, ADBE, TTWO, NFLX, LDOS, BKR,
# CTSH.
#
# *** PRIOR-KNOWLEDGE CONTEXT, DISCLOSED UP FRONT ***
# GST_Task5_GSTSamplingNoise.py already found that Google Trends serves
# FULLY-CLOSED historical periods deterministically (zero noise across
# repeated pulls), and only the CURRENT/PARTIAL week shows real run-to-run
# sampling noise. All 10 events here are old, fully-closed weeks, so this
# audit is expected to replicate that prior finding, not contradict it —
# stated here so a "0 variance" result reads as confirmation, not a
# surprise being glossed over.
#
# PART A — reproducibility: for each event, pull the SAME query (ticker
# term, cat=0/All, US, Web Search) 10 separate times, each as an
# independent ~300-day-lookback weekly pull ending the week after the
# event (matches PULL_LOOKBACK_DAYS=300 convention from
# GST_Live_Signal_Engine.py), recompute the z-score with the IDENTICAL
# production formula (12-week rolling window, min_periods=8, shift(1))
# each time.
#
# PART B — term/category sensitivity: for each event, one additional pull
# each with (a) the company's common name instead of the ticker symbol,
# same cat=0, and (b) the ticker symbol with cat=7 (Google's "Finance"
# category, confirmed via pytrends.categories()) instead of cat=0/All.
#
# Output: Live Signal Engine/GST_Reproducibility_Audit.csv

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import random
import sys
import time
import numpy as np
import pandas as pd
import urllib3
from pytrends.request import TrendReq

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

EVENTS = [
    {"ticker": "MSFT", "spike_week": "2021-07-25", "orig_zscore": 5.682, "company": "Microsoft"},
    {"ticker": "SBUX", "spike_week": "2021-07-25", "orig_zscore": 5.332, "company": "Starbucks"},
    {"ticker": "NVDA", "spike_week": "2022-02-13", "orig_zscore": 5.716, "company": "NVIDIA"},
    {"ticker": "INTC", "spike_week": "2022-07-24", "orig_zscore": 9.734, "company": "Intel"},
    {"ticker": "ADBE", "spike_week": "2023-03-12", "orig_zscore": 5.663, "company": "Adobe"},
    {"ticker": "TTWO", "spike_week": "2023-11-05", "orig_zscore": 25.302, "company": "Take-Two Interactive"},
    {"ticker": "NFLX", "spike_week": "2024-10-13", "orig_zscore": 16.230, "company": "Netflix"},
    {"ticker": "LDOS", "spike_week": "2024-10-27", "orig_zscore": 6.833, "company": "Leidos"},
    {"ticker": "BKR", "spike_week": "2025-07-20", "orig_zscore": 9.706, "company": "Baker Hughes"},
    {"ticker": "CTSH", "spike_week": "2025-07-27", "orig_zscore": 5.114, "company": "Cognizant"},
]

N_REPRO_PULLS = 10
PULL_LOOKBACK_DAYS = 300
POST_EVENT_BUFFER_DAYS = 7   # end date = spike_week + this, so the event's own week is fully closed

GEO, GPROP = "US", ""
CAT_ALL, CAT_FINANCE = 0, 7

ROLLING_WINDOW = 12
MIN_PERIODS = 8
STRONG_TIER_Z_THRESHOLD = 5.0
STABILITY_MIN_HITS = 8   # flag "unstable" if fewer than this many of 10 pulls clear z>=5

MAX_ATTEMPTS = 5
HARD_429_SLEEP = 60
BETWEEN_CALLS_S = (2.0, 4.0)

OUT_PATH = Path("Live Signal Engine") / "GST_Reproducibility_Audit.csv"


def fetch_gst(pt: TrendReq, term: str, start: str, end: str, cat: int) -> pd.DataFrame:
    timeframe = f"{start} {end}"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            pt.build_payload([term], timeframe=timeframe, geo=GEO, gprop=GPROP, cat=cat)
            df = pt.interest_over_time()
            if df is None or df.empty or term not in df.columns:
                raise RuntimeError("Empty result or missing term column")
            out = pd.DataFrame({
                "Week": pd.to_datetime(df.index),
                "gst": pd.to_numeric(df[term], errors="coerce").fillna(0),
            }).sort_values("Week").reset_index(drop=True)
            return out
        except Exception as e:
            msg = str(e).lower()
            pause = HARD_429_SLEEP if ("429" in msg or "too many" in msg or "rate" in msg) else min(6, 2 * attempt) + random.uniform(0, 0.5)
            print(f"    attempt {attempt} failed ({term}, cat={cat}): {e} -- sleeping {pause:.1f}s")
            time.sleep(pause)
    return pd.DataFrame(columns=["Week", "gst"])


def zscore_at_week(weekly: pd.DataFrame, target_week: pd.Timestamp) -> float | None:
    if weekly.empty:
        return None
    shifted = weekly["gst"].shift(1)
    roll = shifted.rolling(window=ROLLING_WINDOW, min_periods=MIN_PERIODS)
    z = (weekly["gst"] - roll.mean()) / roll.std()
    z = z.replace([np.inf, -np.inf], np.nan)
    match = weekly.loc[weekly["Week"] == target_week]
    if match.empty:
        # nearest week within a few days, in case of a minor index misalignment
        gaps = (weekly["Week"] - target_week).abs()
        idx = gaps.idxmin()
        if gaps.loc[idx] > pd.Timedelta(days=3):
            return None
        return float(z.loc[idx]) if pd.notna(z.loc[idx]) else None
    idx = match.index[0]
    return float(z.loc[idx]) if pd.notna(z.loc[idx]) else None


def main():
    print("*** GST REPRODUCIBILITY AUDIT — 10 STRONG_EARNINGS events ***\n")
    pt = TrendReq(hl="en-US", tz=0, timeout=(30, 60), retries=0, backoff_factor=0.0, requests_args={"verify": False})

    rows = []

    for ev in EVENTS:
        ticker, company = ev["ticker"], ev["company"]
        spike_week = pd.Timestamp(ev["spike_week"])
        end = (spike_week + timedelta(days=POST_EVENT_BUFFER_DAYS)).strftime("%Y-%m-%d")
        start = (spike_week + timedelta(days=POST_EVENT_BUFFER_DAYS) - timedelta(days=PULL_LOOKBACK_DAYS)).strftime("%Y-%m-%d")

        print(f"=== {ticker} ({spike_week.date()}, original z={ev['orig_zscore']:.3f}) ===")

        # --- PART A: reproducibility, 10 repeated pulls, raw ticker, cat=0 ---
        repro_zscores = []
        for i in range(1, N_REPRO_PULLS + 1):
            weekly = fetch_gst(pt, ticker, start, end, CAT_ALL)
            z = zscore_at_week(weekly, spike_week)
            repro_zscores.append(z)
            print(f"  [repro pull {i}/{N_REPRO_PULLS}] z={z}")
            rows.append({"ticker": ticker, "spike_week": spike_week.date(), "orig_zscore": ev["orig_zscore"],
                         "test": "reproducibility", "pull_num": i, "term": ticker, "category": "All (0)",
                         "zscore": round(z, 4) if z is not None else None,
                         "clears_z5": (z is not None and z >= STRONG_TIER_Z_THRESHOLD)})
            time.sleep(random.uniform(*BETWEEN_CALLS_S))

        valid = [z for z in repro_zscores if z is not None]
        n_clear = sum(1 for z in valid if z >= STRONG_TIER_Z_THRESHOLD)
        z_range = (max(valid) - min(valid)) if valid else None
        z_std = float(np.std(valid, ddof=1)) if len(valid) > 1 else None
        unstable = n_clear < STABILITY_MIN_HITS
        print(f"  n_valid={len(valid)}/{N_REPRO_PULLS}  n_clear_z5={n_clear}/{N_REPRO_PULLS}  "
              f"range={z_range}  std={z_std}  {'*** UNSTABLE ***' if unstable else 'stable'}\n")

        # --- PART B: term/category sensitivity ---
        weekly_company = fetch_gst(pt, company, start, end, CAT_ALL)
        z_company = zscore_at_week(weekly_company, spike_week)
        print(f"  [company-name pull] term='{company}' z={z_company}")
        rows.append({"ticker": ticker, "spike_week": spike_week.date(), "orig_zscore": ev["orig_zscore"],
                     "test": "term_sensitivity", "pull_num": None, "term": company, "category": "All (0)",
                     "zscore": round(z_company, 4) if z_company is not None else None,
                     "clears_z5": (z_company is not None and z_company >= STRONG_TIER_Z_THRESHOLD)})
        time.sleep(random.uniform(*BETWEEN_CALLS_S))

        weekly_finance = fetch_gst(pt, ticker, start, end, CAT_FINANCE)
        z_finance = zscore_at_week(weekly_finance, spike_week)
        print(f"  [finance-category pull] term='{ticker}' cat=Finance(7) z={z_finance}\n")
        rows.append({"ticker": ticker, "spike_week": spike_week.date(), "orig_zscore": ev["orig_zscore"],
                     "test": "category_sensitivity", "pull_num": None, "term": ticker, "category": "Finance (7)",
                     "zscore": round(z_finance, 4) if z_finance is not None else None,
                     "clears_z5": (z_finance is not None and z_finance >= STRONG_TIER_Z_THRESHOLD)})
        time.sleep(random.uniform(*BETWEEN_CALLS_S))

        # summary row per event
        rows.append({"ticker": ticker, "spike_week": spike_week.date(), "orig_zscore": ev["orig_zscore"],
                     "test": "EVENT_SUMMARY", "pull_num": None, "term": None, "category": None,
                     "zscore": None, "clears_z5": None,
                     "n_valid_repro_pulls": len(valid), "n_clearing_z5": n_clear,
                     "zscore_range": round(z_range, 4) if z_range is not None else None,
                     "zscore_std": round(z_std, 4) if z_std is not None else None,
                     "flagged_unstable": unstable,
                     "zscore_company_name": round(z_company, 4) if z_company is not None else None,
                     "zscore_finance_category": round(z_finance, 4) if z_finance is not None else None})

    result = pd.DataFrame(rows)
    result.to_csv(OUT_PATH, index=False)
    print(f"Wrote: {OUT_PATH}\n")

    summaries = result[result["test"] == "EVENT_SUMMARY"]
    print("=== OVERALL SUMMARY ===")
    print(summaries[["ticker", "spike_week", "orig_zscore", "n_clearing_z5", "zscore_range", "zscore_std",
                      "flagged_unstable", "zscore_company_name", "zscore_finance_category"]].to_string(index=False))

    n_unstable = summaries["flagged_unstable"].sum()
    print(f"\n{n_unstable}/{len(summaries)} events flagged UNSTABLE (fewer than {STABILITY_MIN_HITS}/10 repeated pulls cleared z>=5).")
    avg_range = summaries["zscore_range"].mean()
    print(f"Average z-score range across 10 repeated pulls: {avg_range:.4f}")


if __name__ == "__main__":
    main()
