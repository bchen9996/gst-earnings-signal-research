#!/usr/bin/env python3
# GST Weekly Data Gathering — 2021-2025 replication window. Same 15
# original tickers, same methodology (US, Web Search, All categories,
# cat=0) as the original 2014-2019 pull, shifted to a recent 5-year window
# to test whether the core findings survived into the modern market regime
# (post-retail-options-boom, post-COVID, post-meme-stock era) — the actual
# regime the live forward test (GST_Live_Signal_Engine.py) is running in.
#
# Writes: GST Data/Weekly Data (2021-2025)/<TICKER>_<YEAR>.csv

from __future__ import annotations
from pathlib import Path
import sys, time, random
import pandas as pd
import urllib3
from pytrends.request import TrendReq

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

TICKERS = [
    "TSLA","NVDA","AAPL","MSFT","AMZN",
    "GOOGL","NFLX","ADBE","NKE","SBUX",
    "INTC","TTWO","QCOM","GME","EBAY"
]

START_YEAR = 2021
END_YEAR   = 2025
YEARS = list(range(START_YEAR, END_YEAR + 1))

GEO = "US"
GPROP = ""
CATEGORY = 0   # All categories — matches the original baseline methodology

OUTDIR = Path("GST Data") / "Weekly Data (2021-2025)"
OUTDIR.mkdir(parents=True, exist_ok=True)

BETWEEN_YEARS   = (1.0, 2.0)
BETWEEN_TICKERS = (1.5, 3.0)
BATCH_SIZE      = 6
BATCH_PAUSE_S   = 20
HARD_429_SLEEP  = 60

def fetch_one_year(pt: TrendReq, term: str, year: int) -> pd.DataFrame:
    timeframe = f"{year}-01-01 {year}-12-31"
    MAX_ATTEMPTS = 5
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            pt.build_payload([term], timeframe=timeframe, geo=GEO, gprop=GPROP, cat=CATEGORY)
            df = pt.interest_over_time()
            if df is None or df.empty or term not in df.columns:
                raise RuntimeError("Empty result or missing term column")

            out = pd.DataFrame({
                "Week": df.index.date,
                term: pd.to_numeric(df[term], errors="coerce").fillna(0).round(0).astype(int),
                "isPartial": df["isPartial"].astype(bool)
            })
            out = out[(pd.to_datetime(out["Week"]).dt.year == year)]
            return out
        except Exception as e:
            msg = str(e).lower()
            pause = HARD_429_SLEEP if ("429" in msg or ("rate" in msg and "limit" in msg) or "too many" in msg) \
                   else min(6, 2 * attempt) + random.uniform(0, 0.5)
            print(f"[{term} {year}] attempt {attempt} failed: {e} — sleeping {pause:.1f}s")
            time.sleep(pause)

    return pd.DataFrame(columns=["Week", term, "isPartial"])

def main():
    print(f"Fetching WEEKLY Google Trends for {len(TICKERS)} tickers "
          f"(US, {START_YEAR}–{END_YEAR}, Web Search, All categories)…\n")

    pt = TrendReq(hl="en-US", tz=0, timeout=(30, 60), retries=0, backoff_factor=0.0,
                  requests_args={"verify": False})

    for i, term in enumerate(TICKERS, start=1):
        total_rows = 0
        for yr in YEARS:
            out_path = OUTDIR / f"{term}_{yr}.csv"
            df = fetch_one_year(pt, term, yr)

            if df.empty:
                out_path.write_text(f"Week,{term},isPartial\n", encoding="utf-8")
                print(f"[{term}] {yr}: FAILED — wrote header-only CSV")
            else:
                df.to_csv(out_path, index=False, encoding="utf-8")
                mx = int(df[term].max())
                weeks = len(df)
                total_rows += weeks
                print(f"[{term}] {yr}: wrote {weeks} weeks → {out_path.name} (max={mx})")

            time.sleep(random.uniform(*BETWEEN_YEARS))

        print(f"[{term}] total rows across {START_YEAR}-{END_YEAR}: {total_rows}")

        time.sleep(random.uniform(*BETWEEN_TICKERS))
        if i % BATCH_SIZE == 0 and i != len(TICKERS):
            print(f"— small batch pause ({BATCH_PAUSE_S}s) —")
            time.sleep(BATCH_PAUSE_S)

    print("\nDone. CSVs are in:", OUTDIR.resolve())

if __name__ == "__main__":
    main()
