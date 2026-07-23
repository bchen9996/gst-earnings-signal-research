#!/usr/bin/env python3
# GST Historical Spike Frequency Prior — 51-ticker 2021-2025 universe.
#
# For each ticker, computes: of its total earnings quarters in the 2021-2025
# window, what fraction produced a STRONG_EARNINGS event (a z>=4 GST spike
# within 5 days of that quarter's earnings date)? Ranks tickers by this
# historical rate to prioritize which names to watch closely heading into
# their next earnings date.
#
# *** THIS IS A HISTORICAL BASE RATE, NOT A PREDICTION ***
# A high historical rate means this ticker's search interest has spiked
# around earnings frequently in the past. It does NOT mean it WILL spike
# next time. Small per-ticker denominators (16-20 quarters) mean single-
# digit percentage-point differences in rate can come down to 1-2 events —
# read the raw counts, not just the rate, before treating a ranking as
# meaningful. This is component 1 of a planned two-part signal; component 2
# (earnings estimate revision acceleration) needs 3-4 weeks of accumulated
# Zacks snapshots before it can be built and is deliberately deferred.
#
# *** DATA SOURCING DISCLOSURE ***
# The z>=4 spike detection (numerator) is 100% on-disk: reuses the existing
# Conjunction Zscore (2021-2025)/ and Conjunction Zscore (2021-2025 Broad50
# Clear)/ zconjunction files, no new GST pulls.
# The total-earnings-quarters count (denominator) and next-earnings-date
# CANNOT be recovered from disk: the earlier earnings-clustering scripts
# (GST_Earnings_Clustering_Test_2021_2025*.py) computed each spike event's
# gap-to-nearest-earnings-date in memory and only ever persisted the
# resulting flags (spike_event_earnings_flags.csv) — never the raw earnings
# date list itself. Getting an accurate denominator requires one lightweight
# yfinance get_earnings_dates() pull per ticker (the same endpoint those
# scripts already used) — this script does that pull once per ticker and
# reuses it for both the historical quarter count AND the next-upcoming-
# earnings-date fields, rather than pulling earnings dates twice.
#
# Output: Live Signal Engine/historical_spike_frequency_prior.csv

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import sys, time
import urllib3
import requests
import pandas as pd
import yfinance as yf

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

TICKERS_ORIGINAL = [
    "TSLA", "NVDA", "AAPL", "MSFT", "AMZN",
    "GOOGL", "NFLX", "ADBE", "NKE", "SBUX",
    "INTC", "TTWO", "QCOM", "GME", "EBAY",
]
TICKERS_BROAD50_CLEAR = [
    'ABBV', 'ADP', 'ALB', 'ALLE', 'AVB', 'BKR', 'BRK-B', 'CCL', 'COF', 'COHR',
    'CTSH', 'CTVA', 'DELL', 'DVN', 'ERIE', 'GPC', 'GPN', 'JBL', 'LDOS', 'LNT',
    'MCHP', 'MCK', 'MDT', 'NCLH', 'PKG', 'PLD', 'PNW', 'RCL', 'REG', 'ROP',
    'RTX', 'STZ', 'SYF', 'SYK', 'UAL', 'XOM',
]
ALL_TICKERS = TICKERS_ORIGINAL + TICKERS_BROAD50_CLEAR

SPIKE_DIRS = {t: Path("Conjunction Zscore (2021-2025)") for t in TICKERS_ORIGINAL}
SPIKE_DIRS.update({t: Path("Conjunction Zscore (2021-2025 Broad50 Clear)") for t in TICKERS_BROAD50_CLEAR})

Z_THRESHOLD = 4.0
EARNINGS_WINDOW_DAYS = 5   # matches GST_EarningsAdjacent_SpikeVsNoSpike_Test.py's within_5d definition
HIST_WINDOW_START = pd.Timestamp("2021-01-01")
HIST_WINDOW_END = pd.Timestamp("2025-12-31")
EARNINGS_PULL_LIMIT = 40   # covers ~20 quarters back to 2021 plus buffer plus next upcoming; well under Yahoo's 100 cap

OUT_DIR = Path("Live Signal Engine")
OUT_DIR.mkdir(parents=True, exist_ok=True)

SESSION = requests.Session()
SESSION.verify = False
SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


def load_z4_spike_dates(ticker: str) -> list[pd.Timestamp]:
    p = SPIKE_DIRS[ticker] / f"{ticker}_zconjunction.csv"
    if not p.exists():
        return []
    df = pd.read_csv(p)
    df["spike_week"] = pd.to_datetime(df["spike_week"], errors="coerce")
    hits = df[(df["zscore"] >= Z_THRESHOLD) & df["spike_week"].notna()]
    return sorted(hits["spike_week"].tolist())


def fetch_earnings_dates(ticker: str) -> list[pd.Timestamp]:
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


def main():
    print(f"Building historical spike-frequency prior for {len(ALL_TICKERS)} tickers "
          f"(2021-2025 window, z>={Z_THRESHOLD}, within {EARNINGS_WINDOW_DAYS}d of earnings)\n")

    today = datetime.now(timezone.utc).date()
    rows = []
    for i, ticker in enumerate(ALL_TICKERS, start=1):
        z4_dates = load_z4_spike_dates(ticker)
        earnings_dates = fetch_earnings_dates(ticker)

        window_dates = [d for d in earnings_dates if HIST_WINDOW_START <= d <= HIST_WINDOW_END]
        future_dates = [d for d in earnings_dates if d.date() >= today]

        total_quarters = len(window_dates)

        matched = set()
        for spike_date in z4_dates:
            nearest = None
            nearest_gap = None
            for ed in window_dates:
                gap = abs((spike_date - ed).days)
                if nearest_gap is None or gap < nearest_gap:
                    nearest_gap = gap
                    nearest = ed
            if nearest is not None and nearest_gap <= EARNINGS_WINDOW_DAYS:
                matched.add(nearest)

        strong_earnings_quarters = len(matched)
        rate = (strong_earnings_quarters / total_quarters) if total_quarters > 0 else None

        next_earnings = min(future_dates) if future_dates else None
        days_until = (next_earnings.date() - today).days if next_earnings is not None else None

        note = ""
        if total_quarters == 0:
            note = "no earnings dates found in 2021-2025 window — rate undefined"
        elif not (16 <= total_quarters <= 20):
            note = f"quarter count outside expected 16-20 range ({total_quarters})"

        rows.append({
            "ticker": ticker,
            "historical_spike_rate": round(rate, 4) if rate is not None else None,
            "strong_earnings_quarters": strong_earnings_quarters,
            "total_quarters_2021_2025": total_quarters,
            "next_earnings_date": next_earnings.date().isoformat() if next_earnings is not None else None,
            "days_until_next_earnings": days_until,
            "note": note,
        })
        print(f"[{i}/{len(ALL_TICKERS)}] {ticker}: {strong_earnings_quarters}/{total_quarters} quarters "
              f"({'n/a' if rate is None else f'{rate*100:.1f}%'}) "
              f"next_earnings={rows[-1]['next_earnings_date']} ({days_until}d)"
              f"{'  [' + note + ']' if note else ''}")

        time.sleep(0.6)

    result = pd.DataFrame(rows)
    result = result.sort_values(
        by=["historical_spike_rate", "strong_earnings_quarters"],
        ascending=[False, False],
        na_position="last",
    ).reset_index(drop=True)

    out_path = OUT_DIR / "historical_spike_frequency_prior.csv"
    result.to_csv(out_path, index=False)

    print(f"\n=== RANKED HISTORICAL SPIKE FREQUENCY PRIOR (n={len(result)} tickers) ===")
    print("*** Historical base rate only — NOT a prediction. See script header. ***\n")
    print(result.to_string(index=False))

    n_flagged = (result["note"] != "").sum()
    if n_flagged:
        print(f"\n{n_flagged} ticker(s) flagged with data-quality notes — see 'note' column.")

    print(f"\nWrote ranked prior to: {out_path}")


if __name__ == "__main__":
    main()
