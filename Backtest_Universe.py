#!/usr/bin/env python3
# Point-in-time backtest — Step A: build the test universe.
#
# Random sample of 150 tickers from CURRENT S&P 500 membership (fixed seed,
# not hand-picked or sector-matched), used to avoid the hindsight bias of
# testing only today's 26 Zacks Rank=1 names.
#
# *** SURVIVORSHIP / MEMBERSHIP-DATE BIAS DISCLOSURE ***
# This uses TODAY's S&P 500 constituent list applied retroactively over the
# historical test window (2-3 years back). There is no free point-in-time
# source for historical S&P 500 membership, so:
#   - Companies that were removed from the index in that window (bankruptcy,
#     acquisition, demotion) are NOT in this universe, even though they were
#     real, tradeable S&P 500 names at some historical test dates. This
#     biases the sample toward survivors.
#   - Companies added to the index recently ARE in this universe even for
#     test dates before they joined, which is a mild look-ahead on "index
#     membership" (though not on the insider-buying/accruals signals
#     themselves, which are still computed point-in-time from filings).
# This is a real limitation of the backtest, not swept under the rug — it
# means results here likely skew slightly optimistic vs. a true point-in-time
# index reconstruction, but the universe is still 150 names chosen without
# reference to which ones happened to look good later (no cherry-picking).
#
# Output: Stock Screening/Backtest Data/backtest_universe.csv

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

OUT_DIR = Path("Stock Screening") / "Backtest Data"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})
SESSION.verify = False


def main():
    print("Fetching current S&P 500 constituent list from Wikipedia...")
    resp = SESSION.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", timeout=30)
    resp.raise_for_status()
    tables = pd.read_html(io.StringIO(resp.text))
    sp500 = tables[0][["Symbol", "Security", "GICS Sector", "CIK"]].copy()
    sp500["Symbol"] = sp500["Symbol"].str.upper().str.replace(".", "-", regex=False)
    sp500["CIK"] = sp500["CIK"].astype(str).str.zfill(10)
    print(f"Found {len(sp500)} current S&P 500 constituents.")

    rng = random.Random(RANDOM_SEED)
    sampled_symbols = rng.sample(sp500["Symbol"].tolist(), SAMPLE_SIZE)
    sample = sp500[sp500["Symbol"].isin(sampled_symbols)].reset_index(drop=True)
    sample = sample.rename(columns={"Symbol": "ticker", "Security": "company", "CIK": "cik"})
    sample = sample.sort_values("ticker").reset_index(drop=True)

    sample.to_csv(OUT_DIR / "backtest_universe.csv", index=False)

    print(f"\nSampled {len(sample)} tickers (seed={RANDOM_SEED}) from current S&P 500 membership.")
    print("NOTE: current-membership survivorship/look-ahead bias applies — see script header.")
    print(f"\nWrote universe to: {OUT_DIR / 'backtest_universe.csv'}")
    print("\nSector breakdown of sample:")
    print(sample["GICS Sector"].value_counts().to_string())
    print("\nTickers:", ", ".join(sample["ticker"].tolist()))


if __name__ == "__main__":
    main()
