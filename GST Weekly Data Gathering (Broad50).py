#!/usr/bin/env python3
# GST Weekly Data Gathering — Broad50 generalization test. Random sample of
# 50 S&P 500 tickers (fixed seed=42, current membership, excluding the
# original 15 project tickers), US, Web Search, All categories, 2014-2019 —
# same period/methodology as the original project, to test whether the
# volatility finding (+2.976 pts, p=0.0000 on the original 15) replicates
# on an independent, broader ticker sample.
#
# *** SURVIVORSHIP CAVEAT *** same as Backtest_Universe.py: this is TODAY's
# S&P 500 membership applied retroactively to 2014-2019, not a true
# point-in-time index reconstruction. A few sampled tickers (e.g. DELL,
# which went private in 2013 and didn't re-IPO until Dec 2018) will have
# genuine data gaps for parts of this window — that's expected, not a bug,
# and the existing pipeline already handles missing/empty ticker-years
# gracefully (header-only CSVs, skipped downstream).
#
# Writes: GST Data/Weekly Data (Broad50)/<TICKER>_<YEAR>.csv

from __future__ import annotations
from pathlib import Path
import sys, time, random
import pandas as pd
import urllib3
from pytrends.request import TrendReq

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

TICKERS = [
    'ABBV', 'ADP', 'ALB', 'ALLE', 'ARE', 'AVB', 'BKR', 'BRK-B', 'BRO', 'CCL',
    'CI', 'CL', 'COF', 'COHR', 'CTSH', 'CTVA', 'DELL', 'DVN', 'EL', 'ERIE',
    'FE', 'GPC', 'GPN', 'HD', 'JBL', 'KO', 'LDOS', 'LNT', 'LOW', 'MCHP',
    'MCK', 'MDT', 'NCLH', 'NI', 'PKG', 'PLD', 'PM', 'PNW', 'RCL', 'REG',
    'ROP', 'RTX', 'STZ', 'SYF', 'SYK', 'T', 'TT', 'UAL', 'VZ', 'XOM',
]

START_YEAR = 2014
END_YEAR   = 2019
YEARS = list(range(START_YEAR, END_YEAR + 1))

GEO = "US"
GPROP = ""
CATEGORY = 0   # All categories — matches original project methodology

OUTDIR = Path("GST Data") / "Weekly Data (Broad50)"
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
