#!/usr/bin/env python3
# GST Mid-Week Detection Test — does a partial-week (through Tuesday) GST
# reading reliably predict the eventual full-week spike classification?
#
# The already-pulled historical data is WEEKLY granularity only (one
# aggregated number per Sunday-Saturday week) — there is no sub-week
# resolution stored anywhere, so a partial-week value CANNOT be recovered
# from existing data. It has to be reconstructed with a new, separate
# pytrends query per event: a historical request whose date range ends on
# the Tuesday of that spike week (anchor + 2 days) instead of running the
# week to completion. Google Trends treats whatever week is most recent in
# a query as partial and scores it using only the days elapsed so far
# (isPartial=True) — this is exactly the mechanism the live signal engine
# relies on for "today's" partial week, so truncating a HISTORICAL query
# the same way faithfully reconstructs what a live read would have shown
# on that Tuesday, years ago.
#
# For a random sample of 100 (seed=42) of the 310 known spike events, this
# reconstructs the z-score AS OF that Tuesday (rolling 12-week baseline
# computed the same way as everywhere else in this project, but using this
# query's own independently-renormalized values — expected and fine, since
# the comparison is self-contained per event: partial-Tuesday z-score vs
# z>=2.0, not partial value vs the original full-pull's absolute number)
# and reports what fraction had ALREADY crossed z>=2.0 by Tuesday, versus
# only crossing once the full week completed.
#
# Cannot be batched — each event needs a unique truncated end-date, so this
# is 100 independent pytrends requests, one per sampled event.
#
# Output: Mid-Week Detection Test/results.csv

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import random
import sys, time
import numpy as np
import pandas as pd
import urllib3
from pytrends.request import TrendReq

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

TICKERS = [
    "TSLA", "NVDA", "AAPL", "MSFT", "AMZN",
    "GOOGL", "NFLX", "ADBE", "NKE", "SBUX",
    "INTC", "TTWO", "QCOM", "GME", "EBAY",
]
SPIKE_DIR = Path("Conjunction Zscore")

GEO = "US"
GPROP = ""
CATEGORY = 0
LOOKBACK_DAYS = 300       # trailing history for the rolling baseline
PARTIAL_WEEK_OFFSET_DAYS = 2   # anchor (Sunday) + 2 = Tuesday

ROLLING_WINDOW = 12
Z_THRESHOLD = 2.0
MIN_PERIODS = 8

SAMPLE_SIZE = 100
RANDOM_SEED = 42

OUT_DIR = Path("Mid-Week Detection Test")
OUT_DIR.mkdir(parents=True, exist_ok=True)

BETWEEN_REQUESTS = (1.5, 3.0)
BATCH_SIZE = 6
BATCH_PAUSE_S = 20
HARD_429_SLEEP = 60
MAX_ATTEMPTS = 5


def load_all_spike_events() -> list[dict]:
    events = []
    for ticker in TICKERS:
        p = SPIKE_DIR / f"{ticker}_zconjunction.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        for _, row in df.iterrows():
            anchor = pd.to_datetime(row["spike_week"], errors="coerce")
            if pd.isna(anchor):
                continue
            events.append({"ticker": ticker, "anchor": anchor, "full_week_zscore": row["zscore"]})
    return events


def fetch_truncated_series(pt: TrendReq, ticker: str, end_date) -> pd.DataFrame:
    start_date = end_date - timedelta(days=LOOKBACK_DAYS)
    timeframe = f"{start_date.isoformat()} {end_date.isoformat()}"

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            pt.build_payload([ticker], timeframe=timeframe, geo=GEO, gprop=GPROP, cat=CATEGORY)
            df = pt.interest_over_time()
            if df is None or df.empty or ticker not in df.columns:
                raise RuntimeError("Empty result or missing term column")
            out = pd.DataFrame({
                "Week": df.index,
                "gst": pd.to_numeric(df[ticker], errors="coerce"),
                "isPartial": df["isPartial"].astype(bool),
            }).sort_values("Week").reset_index(drop=True)
            return out
        except Exception as e:
            msg = str(e).lower()
            pause = HARD_429_SLEEP if ("429" in msg or ("rate" in msg and "limit" in msg) or "too many" in msg) \
                else min(6, 2 * attempt)
            print(f"  attempt {attempt} failed: {e} — sleeping {pause:.1f}s")
            time.sleep(pause)
    return pd.DataFrame(columns=["Week", "gst", "isPartial"])


def compute_target_week_zscore(series: pd.DataFrame, target_week: pd.Timestamp) -> dict:
    if series.empty:
        return {"zscore": None, "note": "empty series"}

    series = series.copy()
    match = series.index[series["Week"] == target_week]
    if len(match) == 0:
        return {"zscore": None, "note": f"target week {target_week.date()} not found in returned series"}
    target_idx = match[0]

    if target_idx < MIN_PERIODS:
        return {"zscore": None, "note": f"insufficient trailing history ({target_idx} weeks before target)"}

    rolling = series["gst"].shift(1).rolling(window=ROLLING_WINDOW, min_periods=MIN_PERIODS)
    roll_mean = rolling.mean()
    roll_std = rolling.std()
    zscore_series = (series["gst"] - roll_mean) / roll_std
    zscore_series = zscore_series.replace([np.inf, -np.inf], np.nan)

    z = zscore_series.iloc[target_idx]
    if pd.isna(z):
        return {"zscore": None, "note": "z-score undefined (flat baseline)"}

    return {
        "zscore": round(float(z), 3),
        "gst_value": int(series["gst"].iloc[target_idx]) if pd.notna(series["gst"].iloc[target_idx]) else None,
        "is_partial": bool(series["isPartial"].iloc[target_idx]),
        "note": "",
    }


def main():
    all_events = load_all_spike_events()
    print(f"Total known spike events: {len(all_events)}")

    rng = random.Random(RANDOM_SEED)
    sample = rng.sample(all_events, min(SAMPLE_SIZE, len(all_events)))
    print(f"Sampled {len(sample)} events (seed={RANDOM_SEED})\n")

    pt = TrendReq(hl="en-US", tz=0, timeout=(30, 60), retries=0, backoff_factor=0.0,
                  requests_args={"verify": False})

    rows = []
    for i, ev in enumerate(sample, start=1):
        ticker = ev["ticker"]
        anchor = ev["anchor"]
        target_week = anchor  # weekly bucket label = the Sunday anchor itself
        end_date = (anchor + timedelta(days=PARTIAL_WEEK_OFFSET_DAYS)).date()

        print(f"[{i}/{len(sample)}] {ticker} spike week {anchor.date()} "
              f"(full-week z={ev['full_week_zscore']:.3f}) — reconstructing as of {end_date}...")

        series = fetch_truncated_series(pt, ticker, end_date)
        result = compute_target_week_zscore(series, target_week)

        row = {
            "ticker": ticker, "spike_week": anchor.date(), "reconstructed_as_of": end_date,
            "full_week_zscore": ev["full_week_zscore"],
            "partial_week_zscore": result.get("zscore"),
            "partial_week_gst_value": result.get("gst_value"),
            "partial_week_is_partial_flag": result.get("is_partial"),
            "partial_week_already_spike": (result.get("zscore") is not None and result["zscore"] >= Z_THRESHOLD),
            "note": result.get("note", ""),
        }
        rows.append(row)

        status = "ALREADY SPIKE" if row["partial_week_already_spike"] else "not yet"
        print(f"    -> partial-week z={result.get('zscore')} ({status}) {result.get('note', '')}")

        time.sleep(random.uniform(*BETWEEN_REQUESTS))
        if i % BATCH_SIZE == 0 and i != len(sample):
            print(f"— small batch pause ({BATCH_PAUSE_S}s) —")
            time.sleep(BATCH_PAUSE_S)

    results = pd.DataFrame(rows)
    out_path = OUT_DIR / "results.csv"
    results.to_csv(out_path, index=False)

    usable = results[results["partial_week_zscore"].notna()]
    n_usable = len(usable)
    n_already_spike = int(usable["partial_week_already_spike"].sum())

    print(f"\n{'='*60}")
    print(f"Reconstructed {n_usable}/{len(results)} events successfully "
          f"({len(results) - n_usable} failed/unusable — see notes in {out_path})")
    if n_usable > 0:
        frac = n_already_spike / n_usable
        print(f"\nOf successfully reconstructed events, {n_already_spike}/{n_usable} "
              f"({frac*100:.1f}%) had ALREADY crossed z>=2.0 by {['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][PARTIAL_WEEK_OFFSET_DAYS]} "
              f"(day {PARTIAL_WEEK_OFFSET_DAYS} of the spike week).")
        print(f"{n_usable - n_already_spike}/{n_usable} ({(1-frac)*100:.1f}%) only crossed the threshold "
              f"once the full week's data came in.")
        print(f"\nMean partial-week z-score: {usable['partial_week_zscore'].mean():.3f}")
        print(f"Mean full-week z-score (same events, original data): {usable['full_week_zscore'].mean():.3f}")

    print(f"\nWrote full results to: {out_path}")


if __name__ == "__main__":
    main()
