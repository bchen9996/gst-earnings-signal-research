#!/usr/bin/env python3
# GST Earnings Clustering Test — 2021-2025 replication. Same methodology
# as GST_Earnings_Clustering_Test.py, applied to the 2021-2025 spike and
# baseline events.

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import sys
import urllib3
import requests
import pandas as pd
import yfinance as yf

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

TICKERS = [
    "TSLA","NVDA","AAPL","MSFT","AMZN",
    "GOOGL","NFLX","ADBE","NKE","SBUX",
    "INTC","TTWO","QCOM","GME","EBAY"
]

SPIKE_DIR = Path("Conjunction Zscore (2021-2025)")
BASE_DIR = Path("Conjunction Zscore Baseline (2021-2025)")
OUT_DIR = Path("Earnings Clustering Test (2021-2025)")
OUT_DIR.mkdir(parents=True, exist_ok=True)

EARNINGS_PULL_LIMIT = 100   # Yahoo hard-caps this endpoint at 100
WINDOWS_DAYS = [3, 5]
WINDOW_START, WINDOW_END = -7, 13

SESSION = requests.Session()
SESSION.verify = False
SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


def fetch_earnings_dates(ticker: str) -> list:
    tk = yf.Ticker(ticker, session=SESSION)
    try:
        df = tk.get_earnings_dates(limit=EARNINGS_PULL_LIMIT)
    except Exception as e:
        print(f"[{ticker}] earnings pull failed: {e}")
        return []
    if df is None or df.empty:
        return []
    dates = pd.to_datetime(df.index).tz_localize(None).normalize()
    return sorted(dates.tolist())


def nearest_earnings_gap_days(anchor: pd.Timestamp, earnings_dates: list) -> float | None:
    if not earnings_dates:
        return None
    diffs = [abs((anchor - ed).days) for ed in earnings_dates]
    return min(diffs)


def in_window_flag(anchor: pd.Timestamp, earnings_dates: list, lo_offset: int, hi_offset: int) -> bool:
    lo = anchor + timedelta(days=lo_offset)
    hi = anchor + timedelta(days=hi_offset)
    return any(lo <= ed <= hi for ed in earnings_dates)


def build_event_flags(anchor_dir: Path, pattern: str, anchor_col: str, earnings_by_ticker: dict) -> pd.DataFrame:
    rows = []
    for ticker in TICKERS:
        p = anchor_dir / pattern.format(ticker=ticker)
        if not p.exists():
            continue
        df = pd.read_csv(p)
        if anchor_col not in df.columns:
            continue
        earnings_dates = earnings_by_ticker.get(ticker, [])

        for _, row in df.iterrows():
            anchor = pd.to_datetime(row[anchor_col], errors="coerce")
            if pd.isna(anchor):
                continue
            gap = nearest_earnings_gap_days(anchor, earnings_dates)
            rec = {"ticker": ticker, "anchor": anchor.date(), "nearest_earnings_gap_days": gap}
            for w in WINDOWS_DAYS:
                rec[f"within_{w}d"] = in_window_flag(anchor, earnings_dates, -w, w)
            rec["within_full_window"] = in_window_flag(anchor, earnings_dates, WINDOW_START, WINDOW_END)
            rows.append(rec)
    return pd.DataFrame(rows)


def main():
    print(f"Pulling earnings dates for {len(TICKERS)} tickers...\n")
    earnings_by_ticker = {}
    for ticker in TICKERS:
        dates = fetch_earnings_dates(ticker)
        earnings_by_ticker[ticker] = dates
        in_range = [d for d in dates if pd.Timestamp("2020-06-01") <= d <= pd.Timestamp("2026-06-01")]
        print(f"[{ticker}] {len(dates)} earnings dates pulled, {len(in_range)} fall in/near the 2021-2025 window")

    print("\nBuilding spike-event and baseline-event earnings-proximity flags...")
    spike_flags = build_event_flags(SPIKE_DIR, "{ticker}_zconjunction.csv", "spike_week", earnings_by_ticker)
    base_flags = build_event_flags(BASE_DIR, "{ticker}_baseline.csv", "random_week", earnings_by_ticker)

    spike_flags.to_csv(OUT_DIR / "spike_event_earnings_flags.csv", index=False)
    base_flags.to_csv(OUT_DIR / "baseline_event_earnings_flags.csv", index=False)

    print(f"\nSpike events: {len(spike_flags)}   Baseline events: {len(base_flags)}\n")

    print(f"{'Check':<28}{'Spike %':>12}{'Baseline %':>14}{'Spike n':>10}{'Baseline n':>12}")
    for w in WINDOWS_DAYS:
        col = f"within_{w}d"
        sp = spike_flags[col].mean() * 100
        bp = base_flags[col].mean() * 100
        print(f"{'within ' + str(w) + 'd of anchor':<28}{sp:>11.1f}%{bp:>13.1f}%{len(spike_flags):>10}{len(base_flags):>12}")

    sp_full = spike_flags["within_full_window"].mean() * 100
    bp_full = base_flags["within_full_window"].mean() * 100
    print(f"{'within full window (-7,+13)':<28}{sp_full:>11.1f}%{bp_full:>13.1f}%{len(spike_flags):>10}{len(base_flags):>12}")

    print(f"\nMedian gap to nearest earnings date (days):")
    print(f"  Spike events:    {spike_flags['nearest_earnings_gap_days'].median():.1f}")
    print(f"  Baseline events: {base_flags['nearest_earnings_gap_days'].median():.1f}")

    print(f"\nWrote flagged event detail to: {OUT_DIR}")
    print("\n--- Comparison to original 2014-2019 result ---")
    print("2014-2019: within 5d spike=76.1%, baseline=5.1%; median gap spike=4.0d, baseline=29.0d")
    print(f"2021-2025: within 5d spike={sp:.1f}%, baseline={bp:.1f}%; "
          f"median gap spike={spike_flags['nearest_earnings_gap_days'].median():.1f}d, "
          f"baseline={base_flags['nearest_earnings_gap_days'].median():.1f}d")


if __name__ == "__main__":
    main()
