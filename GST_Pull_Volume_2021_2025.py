#!/usr/bin/env python3
# Daily Volume pull (yfinance) — 2021-2025 replication window, 51-ticker
# universe. Added specifically to support GST_PreSpike_PriceVolume_Test_
# EXPLORATORY.py's volume comparison — no existing file in this project
# ever persisted Volume (Daily Excess Returns*.py only kept Close/Adj
# Close), so this is a new, disclosed pull, not a silent gap-fill.
#
# One yf.download() call per ticker spanning the full window (not per-year
# like the excess-return pulls) — cheap: 51 requests total. Extra buffer
# before 2021-01-01 is pulled so a 60-trading-day trailing baseline can be
# computed for early-2021 events without falling short of history.
#
# Output: Daily Volume Data (2021-2025)/<TICKER>_volume.csv  (Date, Volume)

from __future__ import annotations
from pathlib import Path
import sys
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

START = "2020-09-01"   # buffer before 2021-01-01 for the 60-trading-day trailing baseline
END = "2026-01-01"

OUT_DIR = Path("Daily Volume Data (2021-2025)")
OUT_DIR.mkdir(parents=True, exist_ok=True)

SESSION = requests.Session()
SESSION.verify = False
SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


def main():
    print(f"Pulling daily Volume for {len(ALL_TICKERS)} tickers, {START} to {END}...\n")
    n_ok, n_failed = 0, 0
    for i, ticker in enumerate(ALL_TICKERS, start=1):
        try:
            df = yf.download(ticker, start=START, end=END, session=SESSION,
                              auto_adjust=True, progress=False, group_by="column", threads=False)
        except Exception as e:
            print(f"[{i}/{len(ALL_TICKERS)}] {ticker}: FAILED — {e}")
            n_failed += 1
            continue

        if df is None or df.empty or "Volume" not in df.columns:
            print(f"[{i}/{len(ALL_TICKERS)}] {ticker}: no data / no Volume column")
            n_failed += 1
            continue

        vol = df["Volume"]
        if isinstance(vol, pd.DataFrame):
            vol = vol.iloc[:, 0]

        out = pd.DataFrame({
            "Date": pd.to_datetime(vol.index),
            "Volume": vol.values,
        }).dropna().sort_values("Date").reset_index(drop=True)

        out_path = OUT_DIR / f"{ticker}_volume.csv"
        out.to_csv(out_path, index=False)
        print(f"[{i}/{len(ALL_TICKERS)}] {ticker}: wrote {len(out)} rows")
        n_ok += 1

    print(f"\nDone. {n_ok} ok, {n_failed} failed. Files saved in: {OUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
