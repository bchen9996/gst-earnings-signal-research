#!/usr/bin/env python3
# Point-in-time backtest — Step A (S&P 600 / small-cap variant).
#
# Tests a literature-motivated hypothesis: insider-trading signal is
# reported to be strongest in less-followed, smaller-cap stocks (Seyhun,
# Lakonishok & Lee), not large caps with heavy analyst coverage. The
# original 150-name sample was drawn from the S&P 500 (all large caps) —
# this pulls a comparably-sized random sample from the S&P 600 (small-cap
# index) instead, same fixed-seed methodology.
#
# Same survivorship / current-membership-applied-retroactively caveat as
# Backtest_Universe.py — see that file's header for the full disclosure.
#
# Output: Stock Screening/Backtest Data SP600/backtest_universe.csv

from __future__ import annotations
from pathlib import Path
import io
import random
import requests
import urllib3
import pandas as pd

urllib3.disable_warnings()

USER_AGENT = "Harshith Akurati Independent Research hakurati11@gmail.com"
SAMPLE_SIZE = 150
RANDOM_SEED = 42

OUT_DIR = Path("Stock Screening") / "Backtest Data SP600"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})
SESSION.verify = False


def main():
    print("Fetching current S&P 600 constituent list from Wikipedia...")
    resp = SESSION.get("https://en.wikipedia.org/wiki/List_of_S%26P_600_companies", timeout=30)
    resp.raise_for_status()
    tables = pd.read_html(io.StringIO(resp.text))
    sp600 = tables[0][["Symbol", "Security", "GICS Sector", "CIK"]].copy()
    sp600["Symbol"] = sp600["Symbol"].str.upper().str.replace(".", "-", regex=False)
    sp600["CIK"] = sp600["CIK"].astype(str).str.zfill(10)
    print(f"Found {len(sp600)} current S&P 600 constituents.")

    rng = random.Random(RANDOM_SEED)
    sampled_symbols = rng.sample(sp600["Symbol"].tolist(), SAMPLE_SIZE)
    sample = sp600[sp600["Symbol"].isin(sampled_symbols)].reset_index(drop=True)
    sample = sample.rename(columns={"Symbol": "ticker", "Security": "company", "CIK": "cik"})
    sample = sample.sort_values("ticker").reset_index(drop=True)

    sample.to_csv(OUT_DIR / "backtest_universe.csv", index=False)

    print(f"\nSampled {len(sample)} tickers (seed={RANDOM_SEED}) from current S&P 600 membership.")
    print("NOTE: current-membership survivorship/look-ahead bias applies (same caveat as the S&P 500 run).")
    print(f"\nWrote universe to: {OUT_DIR / 'backtest_universe.csv'}")
    print("\nSector breakdown of sample:")
    print(sample["GICS Sector"].value_counts().to_string())
    print("\nTickers:", ", ".join(sample["ticker"].tolist()))


if __name__ == "__main__":
    main()
