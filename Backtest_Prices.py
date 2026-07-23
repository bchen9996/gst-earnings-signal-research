#!/usr/bin/env python3
# Point-in-time backtest — Step C: pull daily prices for the universe + SPY.
#
# Covers from just before the earliest test date to well past the latest
# test date + 180-day forward window, so Step D can look up entry/exit
# prices for any (ticker, test_date, horizon) combination without gaps.
#
# Output: Stock Screening/Backtest Data/backtest_prices.csv  (long format:
#         Date, ticker, close)

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timedelta, timezone
import urllib3
import requests
import pandas as pd
import yfinance as yf

urllib3.disable_warnings()

OUT_DIR = Path("Stock Screening") / "Backtest Data"
OUT_DIR.mkdir(parents=True, exist_ok=True)

LOOKBACK_YEARS = 3
END_BUFFER_DAYS = 210
PRICE_START_BUFFER_DAYS = 15
PRICE_END_BUFFER_DAYS = 200  # past the last test date, to cover its 180d forward window


def main():
    universe = pd.read_csv(OUT_DIR / "backtest_universe.csv")
    tickers = universe["ticker"].tolist()
    all_symbols = sorted(set(tickers + ["SPY"]))

    now = datetime.now(timezone.utc)
    test_date_end = now - timedelta(days=END_BUFFER_DAYS)
    test_date_start = test_date_end - timedelta(days=LOOKBACK_YEARS * 365)

    price_start = (test_date_start - timedelta(days=PRICE_START_BUFFER_DAYS)).strftime("%Y-%m-%d")
    price_end = min(now, test_date_end + timedelta(days=PRICE_END_BUFFER_DAYS)).strftime("%Y-%m-%d")

    print(f"Downloading daily prices for {len(all_symbols)} symbols "
          f"({price_start} to {price_end})...")

    session = requests.Session()
    session.verify = False
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    df = yf.download(all_symbols, start=price_start, end=price_end, session=session,
                      progress=False, auto_adjust=True, group_by="ticker", threads=True)

    rows = []
    missing = []
    for sym in all_symbols:
        try:
            sub = df[sym]["Close"].dropna()
        except (KeyError, TypeError):
            missing.append(sym)
            continue
        if sub.empty:
            missing.append(sym)
            continue
        for dt, val in sub.items():
            rows.append({"Date": dt.date(), "ticker": sym, "close": float(val)})

    long_df = pd.DataFrame(rows).sort_values(["ticker", "Date"])
    out_path = OUT_DIR / "backtest_prices.csv"
    long_df.to_csv(out_path, index=False)

    print(f"\nWrote {len(long_df)} price rows for {long_df['ticker'].nunique()} symbols to: {out_path}")
    if missing:
        print(f"\nWARNING: no price data for {len(missing)} symbols: {missing}")


if __name__ == "__main__":
    main()
