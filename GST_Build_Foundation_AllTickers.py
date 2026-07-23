#!/usr/bin/env python3
# Foundation build for Tasks 1-3 (cross-sectional ranking, EWMA baseline,
# negative controls). Unlike every earlier per-task pull in this project,
# this PERSISTS its outputs as genuinely reusable artifacts, since three
# separate tasks in this round all need the same underlying data:
#   - Live Signal Engine/AllTickers_EarningsDates.csv  (raw earnings date
#     list per ticker, 51 tickers — needed to know, for ANY arbitrary
#     week, which tickers are "in an earnings week," not just the
#     previously-sampled spike/baseline anchors this project has used
#     everywhere else so far)
#   - Live Signal Engine/AllTickers_Sectors.csv  (GICS sector, 51 tickers)
#   - Live Signal Engine/AllTickers_ZscoreSeries.csv  (full weekly z-score
#     history, BOTH simple-rolling (12-week, matches production) and EWMA
#     (halflife=6 weeks) side by side, per ticker, every week 2021-2025 —
#     not just weeks that happened to clear some threshold)

from __future__ import annotations
from pathlib import Path
import sys, time
import numpy as np
import pandas as pd
import requests
import urllib3
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
YEARS = list(range(2021, 2026))

WEEKLY_GST_DIRS = {t: Path("GST Data/Weekly Data (2021-2025)") for t in TICKERS_ORIGINAL}
WEEKLY_GST_DIRS.update({t: Path("GST Data/Weekly Data (2021-2025 Broad50 Clear)") for t in TICKERS_BROAD50_CLEAR})

OUT_DIR = Path("Live Signal Engine")
EARNINGS_OUT = OUT_DIR / "AllTickers_EarningsDates.csv"
SECTOR_OUT = OUT_DIR / "AllTickers_Sectors.csv"
ZSCORE_OUT = OUT_DIR / "AllTickers_ZscoreSeries.csv"

EARNINGS_PULL_LIMIT = 40
ROLLING_WINDOW = 12
MIN_PERIODS = 8
EWMA_HALFLIFE = 6

SESSION = requests.Session()
SESSION.verify = False
SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


def fetch_earnings_dates(ticker: str, max_attempts: int = 3) -> pd.DataFrame:
    df = None
    for attempt in range(1, max_attempts + 1):
        try:
            tk = yf.Ticker(ticker, session=SESSION)
            df = tk.get_earnings_dates(limit=EARNINGS_PULL_LIMIT)
        except Exception as e:
            print(f"  [{ticker}] earnings attempt {attempt} failed: {e}")
            df = None
        if df is not None and not df.empty:
            break
        if attempt < max_attempts:
            time.sleep(5)
    if df is None or df.empty:
        return pd.DataFrame()
    return pd.DataFrame({"date": pd.to_datetime(df.index).tz_localize(None).normalize()}).dropna()


def fetch_sector(ticker: str, max_attempts: int = 3) -> str | None:
    for attempt in range(1, max_attempts + 1):
        try:
            tk = yf.Ticker(ticker, session=SESSION)
            sector = tk.info.get("sector")
            if sector:
                return sector
        except Exception as e:
            print(f"  [{ticker}] sector attempt {attempt} failed: {e}")
        if attempt < max_attempts:
            time.sleep(5)
    return None


def load_full_weekly_series(ticker: str) -> pd.DataFrame:
    frames = []
    for year in YEARS:
        p = WEEKLY_GST_DIRS[ticker] / f"{ticker}_{year}.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        if "Week" not in df.columns or ticker not in df.columns:
            continue
        df = df.rename(columns={ticker: "gst"})[["Week", "gst"]]
        df["Week"] = pd.to_datetime(df["Week"], errors="coerce")
        frames.append(df.dropna(subset=["Week"]))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values("Week").reset_index(drop=True)


def main():
    print(f"*** Building shared foundation for {len(ALL_TICKERS)} tickers ***\n")

    # --- Earnings dates ---
    print("Pulling earnings dates (cached, one call per ticker)...")
    earnings_rows = []
    for i, ticker in enumerate(ALL_TICKERS, start=1):
        dates = fetch_earnings_dates(ticker)
        for d in dates["date"]:
            earnings_rows.append({"ticker": ticker, "earnings_date": d.date().isoformat()})
        print(f"  [{i}/{len(ALL_TICKERS)}] {ticker}: {len(dates)} earnings dates")
        time.sleep(0.8)
    earnings_df = pd.DataFrame(earnings_rows)
    earnings_df.to_csv(EARNINGS_OUT, index=False)
    print(f"Wrote: {EARNINGS_OUT} ({len(earnings_df)} total date records)\n")

    # --- Sectors ---
    print("Pulling GICS sector (cached, one call per ticker)...")
    sector_rows = []
    for i, ticker in enumerate(ALL_TICKERS, start=1):
        sector = fetch_sector(ticker)
        sector_rows.append({"ticker": ticker, "sector": sector or "UNKNOWN"})
        print(f"  [{i}/{len(ALL_TICKERS)}] {ticker}: {sector or 'UNKNOWN'}")
        time.sleep(0.8)
    sector_df = pd.DataFrame(sector_rows)
    sector_df.to_csv(SECTOR_OUT, index=False)
    print(f"Wrote: {SECTOR_OUT}\n")

    # --- Z-score series: simple-rolling AND EWMA, side by side ---
    print("Computing full weekly z-score series (simple-rolling + EWMA) per ticker...")
    z_rows = []
    for ticker in ALL_TICKERS:
        weekly = load_full_weekly_series(ticker)
        if weekly.empty:
            continue
        shifted = weekly["gst"].shift(1)

        simple_roll = shifted.rolling(window=ROLLING_WINDOW, min_periods=MIN_PERIODS)
        z_simple = (weekly["gst"] - simple_roll.mean()) / simple_roll.std()
        z_simple = z_simple.replace([np.inf, -np.inf], np.nan)

        ewma_mean = shifted.ewm(halflife=EWMA_HALFLIFE, min_periods=MIN_PERIODS).mean()
        ewma_std = shifted.ewm(halflife=EWMA_HALFLIFE, min_periods=MIN_PERIODS).std()
        z_ewma = (weekly["gst"] - ewma_mean) / ewma_std
        z_ewma = z_ewma.replace([np.inf, -np.inf], np.nan)

        for w, gst, zs, ze in zip(weekly["Week"], weekly["gst"], z_simple, z_ewma):
            z_rows.append({
                "ticker": ticker, "week": w.date().isoformat(), "gst": gst,
                "zscore_simple": round(float(zs), 4) if pd.notna(zs) else None,
                "zscore_ewma": round(float(ze), 4) if pd.notna(ze) else None,
            })
    z_df = pd.DataFrame(z_rows)
    z_df.to_csv(ZSCORE_OUT, index=False)
    print(f"Wrote: {ZSCORE_OUT} ({len(z_df)} (ticker, week) rows)\n")

    print("Foundation build complete.")


if __name__ == "__main__":
    main()
