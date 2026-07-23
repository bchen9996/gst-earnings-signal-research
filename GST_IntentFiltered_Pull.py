#!/usr/bin/env python3
# GST Intent-Filtered Pull — "[TICKER] earnings" search term, 2021-2025,
# for the 8 highest-frequency tickers. Tests whether earnings-specific
# search intent is a cleaner signal than raw ticker-symbol attention.
#
# Same per-year pull pattern as "GST Weekly Data Gathering (2021-2025
# Broad50 Clear).py" (each year pulled independently -> guarantees WEEKLY
# granularity within each request; years concatenated afterward for the
# rolling z-score). 45s between calls per this test's explicit request
# (wider than the standard 1.5-3.0s ticker gap and 20s batch pause used
# elsewhere in this project) to avoid the sustained 429s seen in recent
# live-engine batches.
#
# Output: GST Data/Weekly Data (Intent Filtered Earnings)/<TICKER>_<YEAR>.csv

from __future__ import annotations
from pathlib import Path
import sys, time, random
import pandas as pd
import urllib3
from pytrends.request import TrendReq

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

TICKERS = ["MSFT", "ADBE", "NFLX", "NKE", "STZ", "QCOM", "SBUX", "AMZN"]

START_YEAR = 2021
END_YEAR = 2025
YEARS = list(range(START_YEAR, END_YEAR + 1))

GEO = "US"
GPROP = ""
CATEGORY = 0

OUTDIR = Path("GST Data") / "Weekly Data (Intent Filtered Earnings)"
OUTDIR.mkdir(parents=True, exist_ok=True)

BETWEEN_CALLS_S = 45.0
HARD_429_SLEEP = 60
MAX_ATTEMPTS = 5


def fetch_one_year(pt: TrendReq, term: str, year: int) -> pd.DataFrame:
    timeframe = f"{year}-01-01 {year}-12-31"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            pt.build_payload([term], timeframe=timeframe, geo=GEO, gprop=GPROP, cat=CATEGORY)
            df = pt.interest_over_time()
            if df is None or df.empty or term not in df.columns:
                raise RuntimeError("Empty result or missing term column")

            out = pd.DataFrame({
                "Week": df.index.date,
                "gst": pd.to_numeric(df[term], errors="coerce").fillna(0).round(0).astype(int),
                "isPartial": df["isPartial"].astype(bool),
            })
            out = out[(pd.to_datetime(out["Week"]).dt.year == year)]
            return out
        except Exception as e:
            msg = str(e).lower()
            pause = HARD_429_SLEEP if ("429" in msg or ("rate" in msg and "limit" in msg) or "too many" in msg) \
                else min(6, 2 * attempt) + random.uniform(0, 0.5)
            print(f"[{term} {year}] attempt {attempt} failed: {e} — sleeping {pause:.1f}s")
            time.sleep(pause)

    return pd.DataFrame(columns=["Week", "gst", "isPartial"])


def main():
    print(f"Fetching WEEKLY Google Trends for {len(TICKERS)} intent-filtered terms "
          f"(US, {START_YEAR}-{END_YEAR}, Web Search, All categories), "
          f"query = '<TICKER> earnings', {BETWEEN_CALLS_S:g}s between calls...\n")

    pt = TrendReq(hl="en-US", tz=0, timeout=(30, 60), retries=0, backoff_factor=0.0,
                  requests_args={"verify": False})

    for i, ticker in enumerate(TICKERS, start=1):
        term = f"{ticker} earnings"
        total_rows = 0
        for yr in YEARS:
            out_path = OUTDIR / f"{ticker}_{yr}.csv"
            df = fetch_one_year(pt, term, yr)

            if df.empty:
                out_path.write_text("Week,gst,isPartial\n", encoding="utf-8")
                print(f"[{ticker}] {yr}: FAILED — wrote header-only CSV")
            else:
                df.to_csv(out_path, index=False, encoding="utf-8")
                mx = int(df["gst"].max())
                weeks = len(df)
                total_rows += weeks
                print(f"[{ticker}] {yr}: wrote {weeks} weeks -> {out_path.name} (max={mx})")

            print(f"— sleeping {BETWEEN_CALLS_S:g}s —")
            time.sleep(BETWEEN_CALLS_S)

        print(f"[{ticker}] total rows across {START_YEAR}-{END_YEAR}: {total_rows}\n")

    print("Done. CSVs are in:", OUTDIR.resolve())


if __name__ == "__main__":
    main()
