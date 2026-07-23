#!/usr/bin/env python3
# TASK 3 — Market cap buckets: does the STRONG_EARNINGS (z>=5) edge differ
# by company size? New lightweight yfinance pull (51 tickers, cached).
#
# *** LOOK-AHEAD DISCLOSURE ***
# Market cap is CURRENT (as of when this script runs), applied retroactively
# to classify 2021-2025 historical events. A company's market cap changes
# over years — a name that's large-cap today may have been mid-cap in 2021
# (or vice versa). This is a real, disclosed limitation, not a point-in-time
# reconstruction; no free point-in-time historical market cap source exists
# for this project (same class of limitation as Backtest_Universe.py's
# current-membership S&P 500 disclosure).
#
# Buckets: large cap >$10B, mid cap $2-10B, small cap <$2B.
#
# Output: Live Signal Engine/Task3_MarketCapBuckets_Results.csv

from __future__ import annotations
from pathlib import Path
import sys, time
import pandas as pd
import requests
import urllib3
import yfinance as yf

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
OUT_PATH = Path("Live Signal Engine") / "Task3_MarketCapBuckets_Results.csv"

Z_THRESHOLD = 5.0
LARGE_CAP_MIN = 10e9
MID_CAP_MIN = 2e9

SESSION = requests.Session()
SESSION.verify = False
SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


def fetch_market_cap(ticker: str, max_attempts: int = 3) -> float | None:
    for attempt in range(1, max_attempts + 1):
        try:
            tk = yf.Ticker(ticker, session=SESSION)
            cap = tk.fast_info.get("marketCap") or tk.info.get("marketCap")
            if cap:
                return float(cap)
        except Exception as e:
            print(f"  [{ticker}] attempt {attempt} failed: {e}")
        if attempt < max_attempts:
            time.sleep(5)
    return None


def bucket_for(cap: float | None) -> str:
    if cap is None:
        return "UNKNOWN"
    if cap > LARGE_CAP_MIN:
        return "large_cap_gt10B"
    if cap >= MID_CAP_MIN:
        return "mid_cap_2to10B"
    return "small_cap_lt2B"


def main():
    print(f"*** TASK 3: Market cap buckets (z>={Z_THRESHOLD:g}) ***\n")

    events = pd.read_csv(GROUP_A_PATH)
    events = events[events["zscore"] >= Z_THRESHOLD].copy()
    tickers = sorted(events["ticker"].unique())
    print(f"z>={Z_THRESHOLD:g} STRONG_EARNINGS events: n={len(events)} across {len(tickers)} tickers\n")

    print("Pulling current market cap per ticker (cached, one pull each)...")
    cap_map, bucket_map = {}, {}
    for i, ticker in enumerate(tickers, start=1):
        cap = fetch_market_cap(ticker)
        cap_map[ticker] = cap
        bucket_map[ticker] = bucket_for(cap)
        cap_disp = f"${cap/1e9:.1f}B" if cap else "N/A"
        print(f"  [{i}/{len(tickers)}] {ticker}: {cap_disp} -> {bucket_map[ticker]}")
        time.sleep(0.8)
    print()

    events["market_cap"] = events["ticker"].map(cap_map)
    events["bucket"] = events["ticker"].map(bucket_map)
    win_col, pnl_col = "end_of_spike_week_win", "end_of_spike_week_pnl_pct"

    rows = []
    for bucket, sub in events.groupby("bucket"):
        usable = sub[sub[win_col].notna()]
        n = len(usable)
        if n == 0:
            continue
        rows.append({
            "bucket": bucket, "n": n,
            "win_rate_pct": round(usable[win_col].mean() * 100, 1),
            "avg_pnl_pct": round(usable[pnl_col].mean(), 1),
            "median_pnl_pct": round(usable[pnl_col].median(), 1),
            "tickers": ", ".join(sorted(sub["ticker"].unique())),
        })

    bucket_order = {"large_cap_gt10B": 0, "mid_cap_2to10B": 1, "small_cap_lt2B": 2, "UNKNOWN": 3}
    result = pd.DataFrame(rows)
    result["_order"] = result["bucket"].map(bucket_order)
    result = result.sort_values("_order").drop(columns="_order")
    result.to_csv(OUT_PATH, index=False)

    print("=== MARKET CAP BUCKET BREAKDOWN (spike_week horizon) ===")
    for _, r in result.iterrows():
        print(f"{r['bucket']:<20} n={r['n']:<4} win={r['win_rate_pct']:5.1f}%  "
              f"avg={r['avg_pnl_pct']:+7.1f}%  median={r['median_pnl_pct']:+7.1f}%")

    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
