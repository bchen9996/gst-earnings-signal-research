#!/usr/bin/env python3
# STRONG_EARNINGS backtest — 12 new liquidity-clean tickers, EXTENDED to
# 2015-2020 (in addition to the existing 2021-2025 pull). Kept fully
# separate from the existing 425/51-ticker results, same as the original
# 12-ticker run.
#
# *** PER-TICKER DATA AVAILABILITY, CHECKED NOT ASSUMED ***
# Checked yf.Ticker(t).history(period="max") for all 12 before pulling
# anything. Two tickers don't exist far enough back to have ANY 2015-2020
# data and are skipped entirely for this extension:
#   - SOLS (Solstice Advanced Materials): first price data Oct 2025
#     (2025 Honeywell spinoff) -- doesn't exist in 2015-2020 OR most of
#     2021-2025 either.
#   - DOCS (Doximity): first price data Jun 2021 (IPO) -- doesn't exist
#     in 2015-2020.
#
# *** TICKER-RENAME DATA-VALIDITY ISSUE — DISCOVERED, DISCLOSED ***
# Checking price-history continuity (not just existence) surfaced that two
# more tickers changed NAME/SYMBOL partway through their trading history:
#   - CPRI: continuous price data back to 2011, but this entity traded as
#     "KORS" (Michael Kors Holdings) until it renamed to Capri Holdings /
#     CPRI around Dec 2018 (moderate-high confidence, NOT independently
#     verified against a primary source in this session). Searching the
#     TERM "CPRI" for 2015-2018 would not have meant this company to
#     anyone at the time -- it's a different search term than what
#     investors actually used, so that period is EXCLUDED from this
#     extension. Only 2019-2020 (post-rename) is pulled.
#   - SGI: continuous price data back to 2003, but this is Tempur Sealy
#     International (ticker TPX) until a 2025 corporate action renamed it
#     Somnigroup International / SGI (moderate confidence on exact date,
#     NOT independently verified in this session). This means "SGI" as a
#     search term likely did NOT refer to this company for essentially
#     ALL of 2015-2025, not just the 2015-2020 extension window -- so SGI
#     is EXCLUDED from this extension entirely, and the ORIGINAL 2021-2025
#     SGI result (0 STRONG_EARNINGS events, so it didn't affect the n=8
#     headline anyway) should also be treated as built on a likely-invalid
#     search term, not just an absent one.
#   - PINS (Pinterest): IPO'd April 2019 -- 2015-2018 excluded (didn't
#     exist), 2019-2020 pulled.
# All other tickers (WHR, RMBS, PLNT, SFM, BAH, GAP, AMKR) have stable,
# unambiguous ticker symbols with real price history covering the full
# 2015-2020 window and are extended in full.
#
# Same z-score/dedup/near-earnings/pricing methodology as
# GST_NewTickers12_STRONG_EARNINGS_Backtest.py, reused via import (not
# re-derived), just recomputed over each ticker's full available window
# (so early-2021 weeks that previously had insufficient rolling history
# now get a real z-score instead of NaN, using 2020 data as baseline).
#
# Output: Live Signal Engine/12Ticker_Extended_Backtest.csv
#         (event-level; kept SEPARATE from both the existing 425/51-ticker
#         results AND the original 2021-2025-only 12-ticker result)

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import random
import sys
import time
import pandas as pd
import yfinance as yf
from pytrends.request import TrendReq

sys.stdout.reconfigure(encoding="utf-8")

from GST_NewTickers12_STRONG_EARNINGS_Backtest import (
    GST_OUT_DIR, DAILY_OUT_DIR, BASE_SPIKE_Z_THRESHOLD, STRONG_TIER_Z_THRESHOLD,
    GEO, GPROP, CATEGORY, BETWEEN_YEARS, BETWEEN_TICKERS, BATCH_SIZE, BATCH_PAUSE_S,
    HARD_429_SLEEP, YF_SESSION, fetch_one_year, _dl_prices, compute_zscore, dedupe_spikes,
    fetch_earnings_dates, near_earnings_flag, load_calibrated_near_earnings_markup,
    load_daily_excess, price_event,
)

OUT_PATH = Path("Live Signal Engine") / "12Ticker_Extended_Backtest.csv"

# Per-ticker year ranges for the 2015-2020 extension (disclosed reasons in header above)
EXTENSION_YEARS = {
    "WHR":  list(range(2015, 2021)),
    "RMBS": list(range(2015, 2021)),
    "CPRI": list(range(2019, 2021)),   # renamed from KORS ~Dec 2018 -- pre-rename excluded
    "SOLS": [],                         # doesn't exist (first data Oct 2025) -- fully skipped
    "PLNT": list(range(2015, 2021)),
    "SGI":  [],                         # ticker-rename validity issue -- fully skipped, see header
    "SFM":  list(range(2015, 2021)),
    "DOCS": [],                         # doesn't exist (IPO Jun 2021) -- fully skipped
    "PINS": list(range(2019, 2021)),   # IPO Apr 2019 -- pre-IPO years excluded
    "BAH":  list(range(2015, 2021)),
    "GAP":  list(range(2015, 2021)),
    "AMKR": list(range(2015, 2021)),
}
FULL_YEARS = list(range(2015, 2026))   # union of extension + existing 2021-2025, per-ticker filtered below


def pull_extension_gst():
    print("PHASE 1: pulling 2015-2020 weekly GST for eligible tickers...\n")
    pt = TrendReq(hl="en-US", tz=0, timeout=(30, 60), retries=0, backoff_factor=0.0, requests_args={"verify": False})
    tickers_to_pull = [t for t, yrs in EXTENSION_YEARS.items() if yrs]
    for i, ticker in enumerate(tickers_to_pull, start=1):
        for yr in EXTENSION_YEARS[ticker]:
            out_path = GST_OUT_DIR / f"{ticker}_{yr}.csv"
            if out_path.exists():
                continue
            df = fetch_one_year(pt, ticker, yr)
            if df.empty:
                out_path.write_text(f"Week,{ticker},isPartial\n", encoding="utf-8")
                print(f"  [{ticker}] {yr}: FAILED — header-only")
            else:
                df.to_csv(out_path, index=False, encoding="utf-8")
                print(f"  [{ticker}] {yr}: wrote {len(df)} weeks (max={int(df[ticker].max())})")
            time.sleep(random.uniform(*BETWEEN_YEARS))
        time.sleep(random.uniform(*BETWEEN_TICKERS))
        if i % BATCH_SIZE == 0 and i != len(tickers_to_pull):
            print(f"  — batch pause ({BATCH_PAUSE_S}s) —")
            time.sleep(BATCH_PAUSE_S)
    skipped = [t for t, yrs in EXTENSION_YEARS.items() if not yrs]
    print(f"\nSkipped entirely (no valid 2015-2020 data for this ticker/search-term): {skipped}\n")


def pull_extension_daily():
    print("PHASE 2: pulling 2015-2020 daily prices (ticker + SPY)...\n")
    for ticker, yrs in EXTENSION_YEARS.items():
        for yr in yrs:
            out = DAILY_OUT_DIR / f"{ticker}_{yr}_excess.csv"
            if out.exists():
                continue
            start, end = f"{yr}-01-01", f"{yr+1}-01-01"
            s_tkr, s_spy = _dl_prices(ticker, start, end), _dl_prices("SPY", start, end)
            if s_tkr.empty or s_spy.empty:
                pd.DataFrame(columns=["Date", f"{ticker} Daily Return", "SPY Daily Return", "Excess Daily Return"]).to_csv(out, index=False)
                continue
            r_tkr, r_spy = s_tkr.pct_change().dropna(), s_spy.pct_change().dropna()
            idx = r_tkr.index.intersection(r_spy.index)
            r_tkr, r_spy = r_tkr.loc[idx], r_spy.loc[idx]
            df = pd.DataFrame({"Date": idx, f"{ticker} Daily Return": r_tkr.round(4).values,
                                "SPY Daily Return": r_spy.round(4).values,
                                "Excess Daily Return": (r_tkr - r_spy).round(4).values})
            df.to_csv(out, index=False)
        if yrs:
            print(f"  [{ticker}] extension daily excess returns done")
    print("\nExtension daily pull complete.\n")


def load_daily_excess_full(ticker: str) -> pd.DataFrame:
    """Local replacement for the imported load_daily_excess -- that one is bound to the
    ORIGINAL script's module-level YEARS=[2021..2025] global and silently misses the
    2015-2020 extension files, since Python closures resolve globals in their defining
    module, not the caller's. Loops FULL_YEARS instead."""
    frames = []
    for year in FULL_YEARS:
        p = DAILY_OUT_DIR / f"{ticker}_{year}_excess.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        if "Date" not in df.columns or df.empty:
            continue
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        frames.append(df.dropna(subset=["Date"]))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values("Date").drop_duplicates(subset="Date").reset_index(drop=True)


def load_full_weekly_series(ticker: str) -> pd.DataFrame:
    frames = []
    for year in FULL_YEARS:
        p = GST_OUT_DIR / f"{ticker}_{year}.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        if "Week" not in df.columns or ticker not in df.columns or df.empty:
            continue
        df = df.rename(columns={ticker: "gst"})[["Week", "gst"]]
        df["Week"] = pd.to_datetime(df["Week"], errors="coerce")
        frames.append(df.dropna(subset=["Week"]))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values("Week").drop_duplicates(subset="Week").reset_index(drop=True)


def main():
    print("*** STRONG_EARNINGS BACKTEST — 12 TICKERS, EXTENDED TO 2015-2020 WHERE VALID ***\n")

    pull_extension_gst()
    pull_extension_daily()

    markup = load_calibrated_near_earnings_markup()
    print(f"Using calibrated near-earnings IV markup: {markup:.4f}x realized vol (reused, not re-derived)\n")

    print("Recomputing z-score over each ticker's FULL available window, spike de-dup, near-earnings, pricing...\n")
    all_events = []
    tickers = list(EXTENSION_YEARS.keys())
    for ticker in tickers:
        weekly = load_full_weekly_series(ticker)
        if weekly.empty:
            print(f"  [{ticker}] no GST data at all, skipping")
            continue
        weekly = compute_zscore(weekly)
        deduped = dedupe_spikes(weekly)
        earnings_dates = fetch_earnings_dates(ticker)
        time.sleep(0.5)

        window_desc = f"{weekly['Week'].min().date()} to {weekly['Week'].max().date()}"
        n_strong = 0
        for _, row in deduped.iterrows():
            if pd.isna(row["zscore"]) or row["zscore"] < STRONG_TIER_Z_THRESHOLD:
                continue
            if not near_earnings_flag(row["Week"], earnings_dates):
                continue
            n_strong += 1
            all_events.append({"ticker": ticker, "spike_week": row["Week"], "zscore": row["zscore"], "near_earnings": True})
        print(f"  [{ticker}] window {window_desc}: {len(deduped)} deduped spikes -> {n_strong} STRONG_EARNINGS candidates")

    print(f"\nTotal STRONG_EARNINGS candidate events (extended window): {len(all_events)}\n")

    daily_cache = {t: load_daily_excess_full(t) for t in tickers}
    results = []
    for ev in all_events:
        daily = daily_cache.get(ev["ticker"], pd.DataFrame())
        ret_col = f"{ev['ticker']} Daily Return"
        if daily.empty or ret_col not in daily.columns:
            continue
        priced = price_event(daily, ret_col, ev["spike_week"], markup)
        if priced is None:
            continue
        results.append({**ev, **priced})

    results_df = pd.DataFrame(results)
    if not results_df.empty:
        results_df["spike_week"] = pd.to_datetime(results_df["spike_week"]).dt.date
    results_df.to_csv(OUT_PATH, index=False)
    print(f"Wrote: {OUT_PATH}\n")

    print("=== RESULTS (extended window, kept SEPARATE from existing 425/51-ticker AND the original 2021-2025-only 12-ticker run) ===")
    n = len(results_df)
    print(f"Usable priced STRONG_EARNINGS events: n={n}")
    if n == 0:
        print("No priceable STRONG_EARNINGS events found.")
        return
    win_rate = results_df["win"].mean() * 100
    median_pnl = results_df["pnl_pct"].median()
    mean_pnl = results_df["pnl_pct"].mean()
    print(f"Win rate: {win_rate:.1f}%")
    print(f"Median P&L: {median_pnl:+.1f}%")
    print(f"Mean P&L: {mean_pnl:+.1f}%")
    print(f"\nPer-ticker breakdown:")
    print(results_df.groupby("ticker").agg(n=("win", "size"), win_rate_pct=("win", lambda x: round(x.mean()*100, 1)),
                                            median_pnl_pct=("pnl_pct", lambda x: round(x.median(), 1))).to_string())

    print(f"\n=== COMPARISON ===")
    print(f"Original (2021-2025 only):  n=8   win=75.0%   median=+39.6%")
    print(f"Extended (full window):     n={n}   win={win_rate:.1f}%   median={median_pnl:+.1f}%")
    print(f"(existing 425/51-ticker baseline, for reference only, NOT merged: n=147, win=76.2%, median=+130.0%)")


if __name__ == "__main__":
    main()
